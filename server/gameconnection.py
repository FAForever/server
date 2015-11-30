import asyncio
from collections import defaultdict
from concurrent.futures import CancelledError
import socket
import time
import logging
import functools
import json
import config
from server.abc.base_game import GameConnectionState
from server.connectivity import ConnectivityTest, ConnectivityState, NatHelper
from server.games.game import Game, GameState, Victory
from server.decorators import with_logger, timed
from server.game_service import GameService
from server.players import PlayerState, Player
from server.protocol import GpgNetServerProtocol
import server.db as db

logger = logging.getLogger(__name__)

PROXY_SERVER = ('127.0.0.1', 12000)


class AuthenticationError(Exception):
    pass


@with_logger
class GameConnection(GpgNetServerProtocol, NatHelper):
    """
    Responsible for connections to the game, using the GPGNet protocol
    """

    def __init__(self, loop, lobby_connection, player_service, games: GameService):
        """
        Construct a new GameConnection

        :param loop: asyncio event loop to use
        :param lobby_connection: The lobby connection we're associated with
        :param player_service: PlayerService
        :param games: GamesService
        :return:
        """
        super().__init__()
        self.lobby_connection = lobby_connection
        self._logger.info('GameConnection initializing')
        self._state = GameConnectionState.INITIALIZING
        self._waiters = defaultdict(list)
        self.loop = loop
        self.player_service = player_service
        self.games = games

        self.log = logging.getLogger(__name__)
        self.initTime = time.time()
        self.proxies = {}
        self._player = None
        self.logGame = "\t"
        self._game = None

        self.last_pong = time.time()

        self.ip, self.port = None, None
        self.lobby = None
        self._transport = None
        self.ping_task = None

        self._connectivity_state = asyncio.Future()

    @property
    def state(self):
        """
        :rtype: GameConnectionState
        """
        return self._state

    @property
    def game(self):
        """
        :rtype: Game
        """
        return self._game

    @game.setter
    def game(self, value):
        self._game = value

    @property
    def player(self):
        """
        :rtype: Player
        """
        return self._player

    @player.setter
    def player(self, val):
        self._player = val

    def send_message(self, message):
        self.lobby_connection.send({**message,
                                    'target': 'game'})

    @asyncio.coroutine
    def ping(self):
        """
        Ping the relay server to check if the player is still there.
        """
        while True:
            if self._state == GameConnectionState.ENDED:
                break
            if time.time() - self.last_pong > 30:
                self._logger.debug('Missed ping, terminating')
                self.abort()
                break
            self.send_Ping()
            try:
                yield from asyncio.sleep(20)
            # quamash will yield a runtime error if the qtimer was already deleted
            # asyncio yields a cancelled error which we use to break the loop
            except (RuntimeError, CancelledError):  # pragma: no cover
                break

    async def _handle_idle_state(self):
        """
        This message is sent by FA when it doesn't know what to do.
        :return: None
        """
        assert self.game
        self.send_Ping()
        state = self.player.state

        if state == PlayerState.HOSTING:
            self.game.state = GameState.LOBBY
            self._state = GameConnectionState.CONNECTED_TO_HOST
            self.game.add_game_connection(self)
            self.game.host = self.player
            strlog = (
                "%s.%s.%s\t" % (str(self.player.login), str(self.game.id), str(self.game.game_mode)))
            self.logGame = strlog
            self._send_create_lobby()

        elif state == PlayerState.JOINING:
            strlog = (
                "%s.%s.%s\t" % (str(self.player.login), str(self.game.id), str(self.game.game_mode)))
            self.logGame = strlog
            self._send_create_lobby()

        else:
            self.log.debug("QUIT - No player action :(")
            self.abort()

    @asyncio.coroutine
    def _handle_lobby_state(self):
        """
        The game has told us it is ready and listening on
        self.player.game_port for UDP.
        We determine the connectivity of the peer and respond
        appropriately
        """
        try:
            with ConnectivityTest(self,
                                  self.player.ip,
                                  self.player.game_port,
                                  self.player.id) as peer_test:
                peer_status = yield from peer_test.determine_connectivity()
                if self._connectivity_state.cancelled():
                    return
                self._connectivity_state.set_result(peer_status)
                self.send_gpgnet_message('ConnectivityState', [self.player.id,
                                                               self.connectivity_state.state.value])

            player_state = self.player.state
            if player_state == PlayerState.HOSTING:
                map = self.game.map_file_path
                self.send_HostGame(map)
            # If the player is joining, we connect him to host
            # followed by the rest of the players.
            elif player_state == PlayerState.JOINING:
                yield from self.ConnectToHost(self.game.host.game_connection)
                self._state = GameConnectionState.CONNECTED_TO_HOST
                self.game.add_game_connection(self)
                for peer in self.game.connections:
                    if peer != self and peer.player != self.game.host:
                        self.log.debug("{} connecting to {}".format(self.player, peer))
                        asyncio.async(self.ConnectToPeer(peer))
        except Exception as e:
            self.log.exception(e)

    @timed(limit=0.1)
    async def on_message_received(self, message):
        """
        Main entry point when reading messages
        :param message:
        :return:
        """
        try:
            cmd_id, args = message['action'], message['chunks']
            message["command_id"] = cmd_id
            message["arguments"] = args
            await self.handle_action(cmd_id, args)
            if cmd_id in self._waiters:
                for waiter in self._waiters[cmd_id]:
                    waiter.set_result(message)
                    self._waiters[cmd_id].remove(waiter)
        except ValueError as ex:  # pragma: no cover
            self.log.error("Garbage command {} {}".format(ex, message))

    async def ConnectToHost(self, peer):
        """
        Connect self to a given peer (host)
        :return:
        """
        assert peer.player.state == PlayerState.HOSTING
        connection, own_addr, peer_addr = await self.EstablishConnection(peer)
        if connection == ConnectivityState.PUBLIC or connection == ConnectivityState.STUN:
            self.send_JoinGame(peer_addr,
                               peer.player.login,
                               peer.player.id)
            peer.send_ConnectToPeer(own_addr,
                                    self.player.login,
                                    self.player.id)
        else:
            await self.ConnectThroughProxy(peer)

    async def ConnectToPeer(self, peer):
        """
        Connect two peers
        :return: None
        """
        connection, own_addr, peer_addr = await self.EstablishConnection(peer)
        if connection == ConnectivityState.PUBLIC or connection == ConnectivityState.STUN:
            self.send_ConnectToPeer(peer_addr,
                                    peer.player.login,
                                    peer.player.id)
            peer.send_ConnectToPeer(own_addr,
                                    self.player.login,
                                    self.player.id)
        else:
            self.ConnectThroughProxy(peer)

    async def EstablishConnection(self, peer):
        """
        Attempt to establish a full duplex UDP connection
        between self and peer.

        :param peer: Client to connect to
        :return: (ConnectivityState, own_addr, remote_addr)
        """
        own_state = self._connectivity_state
        peer_state = peer._connectivity_state
        (done, pending) = await asyncio.wait([own_state, peer_state])
        if pending:
            self._logger.debug("Aborting due to lack of connectivity")
            self.abort()
        ((own_addr, own_state), (peer_addr, peer_state)) = own_state.result(), peer_state.result()
        if peer_state == ConnectivityState.PUBLIC and own_state == ConnectivityState.PUBLIC:
            self._logger.debug("Connecting {} to host {} directly".format(self, peer))
            return ConnectivityState.PUBLIC, own_addr, peer_addr
        elif peer_state == ConnectivityState.STUN or own_state == ConnectivityState.STUN:
            self._logger.debug("Connecting {} to host {} using STUN".format(self, peer))
            (own_addr, peer_addr) = await self.STUN(peer)
            if peer_addr is None or own_addr is None:
                self._logger.debug("STUN between {} {} failed".format(self, peer))
                self._logger.debug("Resolved addresses: {}, {}".format(peer_addr, own_addr))
                self._logger.debug("Own nat packets: {}".format(self.nat_packets))
                self._logger.debug("Peer nat packets: {}".format(peer.nat_packets))
            else:
                return ConnectivityState.STUN, own_addr, peer_addr
        self._logger.debug("Connecting {} to host {} through proxy".format(self, peer))
        return ConnectivityState.PROXY, None, None

    async def STUN(self, peer):
        """
        Perform a STUN sequence between self and peer

        :param peer:
        :return: (own_addr, remote_addr) | None
        """
        own_addr = asyncio.ensure_future(self.ProbePeerNAT(peer))
        remote_addr = asyncio.ensure_future(peer.ProbePeerNAT(self))
        (done, pending) = await asyncio.wait([own_addr, remote_addr])
        assert len(pending) == 0
        assert len(done) == 2
        own_addr, remote_addr = own_addr.result(), remote_addr.result()
        if own_addr is not None and remote_addr is not None:
            # Both peers got it the first time
            return own_addr, remote_addr
        if own_addr is not None:
            # Remote received our packet, we didn't receive theirs
            # Instruct remote to try our new address
            remote_addr = await peer.ProbePeerNAT(self, use_address=own_addr)
        elif remote_addr is not None:
            # Opposite of the above
            own_addr = await self.ProbePeerNAT(peer, use_address=remote_addr)
        return own_addr, remote_addr

    async def ProbePeerNAT(self, peer, use_address=None):
        """
        Instruct self to send an identifiable nat packet to peer

        :return: resolved_address
        """
        assert peer.connectivity_state
        nat_message = "Hello from {}".format(self.player.id)
        addr = peer.connectivity_state.addr if not use_address else use_address
        self._logger.debug("{} probing {} at {} with msg: {}".format(self, peer, addr, nat_message))
        for _ in range(3):
            for i in range(0, 4):
                self._logger.debug("{} sending NAT packet {} to {}".format(self, i, addr))
                ip, port = addr.split(":")
                self.send_SendNatPacket("{}:{}".format(ip, int(port) + i), nat_message)
        try:
            waiter = self.wait_for_natpacket(nat_message)
            address, message = await asyncio.wait_for(waiter, 4)
            return address
        except (CancelledError, asyncio.TimeoutError):
            return None

    async def handle_action(self, command, args):
        """
        Handle GpgNetSend messages, wrapped in the JSON protocol
        :param command: command type
        :param arguments: command arguments
        :return: None
        """
        try:
            if command == 'ProcessNatPacket':
                address, message = args[0], args[1]
                self.process_nat_packet(address, message)

            elif command == 'Desync':
                self.game.desyncs += 1

            elif command == 'GameState':
                state = args[0]
                await self.handle_game_state(state)
                self._mark_dirty()

            elif command == 'GameOption':
                option_key = args[0]
                option_value = args[1]
                if option_key == 'Victory':
                    self.game.gameOptions['Victory'] = Victory.from_gpgnet_string(option_value)
                elif option_key in self.game.gameOptions:
                    self.game.gameOptions[option_key] = option_value

                if option_key == "Slots":
                    self.game.max_players = option_value

                if option_key == 'ScenarioFile':
                    raw = "%r" % option_value
                    path = raw.replace('\\', '/')
                    self.game.map_file_path = str(path.split('/')[2]).lower()
                self._mark_dirty()

            elif command == 'GameMods':
                if args[0] == "activated":
                    if args[1] == 0:
                        self.game.mods = {}

                if args[0] == "uids":
                    uids = args[1].split()
                    self.game.mods = {uid: "Unknown sim mod" for uid in uids}
                    async with db.db_pool.get() as conn:
                        cursor = await conn.cursor()
                        await cursor.execute("SELECT uid, name from table_mod WHERE uid in %s", (uids,))
                        mods = await cursor.fetchall()
                        for (uid, name) in mods:
                            self.game.mods[uid] = name
                self._mark_dirty()

            elif command == 'PlayerOption':
                if self.player.state == PlayerState.HOSTING:
                    id = args[0]
                    command = args[1]
                    value = args[2]
                    self.game.set_player_option(int(id), command, value)
                    self._mark_dirty()

            elif command == 'AIOption':
                if self.player.state == PlayerState.HOSTING:
                    name = args[0]
                    command = args[1]
                    value = args[2]
                    self.game.set_ai_option(str(name), command, value)
                    self._mark_dirty()

            elif command == 'ClearSlot':
                if self.player.state == PlayerState.HOSTING:
                    slot = args[0]
                    self.game.clear_slot(slot)
                self._mark_dirty()

            elif command == 'GameResult':
                army = int(args[0])
                result = str(args[1])
                try:
                    if not any(map(functools.partial(str.startswith, result),
                                   ['score', 'defeat', 'victory', 'draw'])):
                        raise ValueError()  # pragma: no cover
                    result = result.split(' ')
                    await self.game.add_result(self.player, army, result[0], int(result[1]))
                except (KeyError, ValueError):  # pragma: no cover
                    self.log.warn("Invalid result for {} reported: {}".format(army, result))
                    pass

            elif command == 'OperationComplete':
                if int(args[0]) == 1:
                    secondary, delta = int(args[1]), str(args[2])
                    with await db.db_pool.get() as conn:
                        cursor = await conn.cursor()
                        # FIXME: Resolve used map earlier than this
                        await cursor.execute("SELECT id FROM coop_map WHERE filename LIKE '%/"
                                             + self.game.map_file_path + ".%'")
                        (mission,) = await cursor.fetchone()
                        if not mission:
                            self._logger.debug("can't find coop map: {}".format(self.game.map_file_path))
                            return

                        await cursor.execute("INSERT INTO `coop_leaderboard`"
                                             "(`mission`, `gameuid`, `secondary`, `time`) "
                                             "VALUES (%s, %s, %s, %s);",
                                             (mission, self.game.id, secondary, delta))
            elif command == 'JsonStats':
                await self.game.report_army_stats(args[0])


        except AuthenticationError as e:
            self.log.exception("Authentication error: {}".format(e))
            self.abort()
        except Exception as e:  # pragma: no cover
            self.log.exception(e)
            self.log.exception(self.logGame + "Something awful happened in a game thread!")
            self.abort()

    def on_ProcessNatPacket(self, address_and_port, message):
        self.nat_packets[message] = address_and_port

    async def handle_game_state(self, state):
        """
        Changes in game state
        :param state: new state
        :return: None
        """
        if state == 'Idle':
            await self._handle_idle_state()
            self._mark_dirty()

        elif state == 'Lobby':
            # The game is initialized and awaiting commands
            # At this point, it is listening locally on the
            # port we told it to (self.player.game_port)
            # We schedule an async task to determine their connectivity
            # and respond appropriately
            #
            # We do not yield from the task, since we
            # need to keep processing other commands while it runs
            asyncio.ensure_future(self._handle_lobby_state())

        elif state == 'Launching':
            if self.player.state == PlayerState.HOSTING:
                await self.game.launch()

                if len(self.game.mods) > 0:
                    async with db.db_pool.get() as conn:
                        cursor = await conn.cursor()
                        await cursor.execute("UPDATE `table_mod` SET `played`= `played`+1  WHERE uid in %s",
                                             (self.game.mods.keys(),))

    def _send_create_lobby(self):
        """
        Used for initializing the game to start listening on UDP
        :param rankedMode int:
            If 1: The game uses autolobby.lua
               0: The game uses lobby.lua
        :return: None
        """
        assert self.game is not None
        if self.game.name is not None:
            if self.game.name.startswith('#'):
                self.send_gpgnet_message("P2PReconnect", [])

        self.send_CreateLobby(self.game.init_mode,
                              self.player.game_port,
                              self.player.login,
                              self.player.id, 1)

    def _mark_dirty(self):
        if self.game:
            self.games.mark_dirty(self.game)

    def abort(self):
        """
        Abort the connection

        Removes the GameConnection object from the any associated Game object,
        and deletes references to Player and Game held by this object.
        """
        try:
            if self._state is GameConnectionState.ENDED:
                return
            self._state = GameConnectionState.ENDED
            if self.game:
                self.loop.create_task(self.game.remove_game_connection(self))
            self._mark_dirty()
            self.log.debug("{}.abort()".format(self))
            del self.player.game
            del self.player.game_connection
        except Exception as ex:  # pragma: no cover
            self.log.debug("Exception in abort(): {}".format(ex))
            pass
        finally:
            if not self._connectivity_state.done():
                self._connectivity_state.cancel()
            if self.ping_task is not None:
                self.ping_task.cancel()
            if self._player:
                self._player.state = PlayerState.IDLE

    def on_connection_lost(self):
        try:
            if self.state == GameConnectionState.CONNECTED_TO_HOST \
                    and self.game.state == GameState.LOBBY:
                for peer in self.game.connections:
                    peer.send_DisconnectFromPeer(self.player.id)
            if self.game:
                if self.game.proxy_map.unmap(self.player.login):
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(PROXY_SERVER)
                    s.sendall(json.dumps(dict(command="cleanup", sourceip=self.player.ip)).encode())
                    s.close()
            if self.connectivity_state and self.connectivity_state.state == ConnectivityState.PROXY:
                wiki_link = "{}index.php?title=Connection_issues_and_solutions".format(config.WIKI_LINK)
                text = "Your network is not setup right.<br>The server had to make you connect to other players by proxy.<br>Please visit <a href='{}'>{}</a>" + \
                       "to fix this.<br><br>The proxy server costs us a lot of bandwidth. It's free to use, but if you are using it often,<br>it would be nice to donate for the server maintenance costs,".format(
                           wiki_link, wiki_link)

                if self.lobby:
                    self.lobby.sendJSON(dict(command="notice", style="info", text=str(text)))
        except Exception as e:  # pragma: no cover
            self._logger.exception(e)
            pass
        finally:
            self.abort()

    @property
    def connectivity_state(self):
        if not self._connectivity_state.done():
            return None
        else:
            return self._connectivity_state.result()

    @connectivity_state.setter
    def connectivity_state(self, val):
        if not self._connectivity_state.done():
            self._connectivity_state.set_result(val)

    def address_and_port(self):
        return "{}:{}".format(self.player.ip, self.player.game_port)

    def __str__(self):
        return "GameConnection(Player({}),Game({}))".format(self.player, self.game)
