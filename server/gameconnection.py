import asyncio

from concurrent.futures import CancelledError
import socket
import time
import logging
import functools

import json
import config

from server.abc.base_game import GameConnectionState
from server.connectivity import TestPeer, ConnectivityState
from server.games.game import Game, GameState, Victory
from server.decorators import with_logger, timed
from server.game_service import GameService
from server.players import PlayerState
from server.protocol import GpgNetServerProtocol
from server.subscribable import Subscribable
import server.db as db


logger = logging.getLogger(__name__)


PROXY_SERVER = ('127.0.0.1', 12000)

@with_logger
class GameConnection(Subscribable, GpgNetServerProtocol):
    """
    Responsible for connections to the game, using the GPGNet protocol
    """
    def __init__(self, loop, player_service, games: GameService):
        """
        Construct a new GameConnection

        :param loop: asyncio event loop to use
        :param player_service: PlayerService
        :param games: GamesService
        :return:
        """
        super().__init__()
        self.protocol = None
        self._logger.info('GameConnection initializing')
        self._state = GameConnectionState.INITIALIZING
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

        self._authenticated = asyncio.Future()
        self.ip, self.port = None, None
        self.lobby = None
        self._transport = None
        self.nat_packets = {}
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
        return self._player

    @player.setter
    def player(self, val):
        self._player = val

    @asyncio.coroutine
    def on_connection_made(self, protocol, peer_name):
        """
        Accept a connected socket for this GameConnection

        Will look up the user using the provided users service,
        followed by obtaining the Game object that the user wishes to join.
        :raise AssertionError
        :return: bool
        """
        self._logger.debug("Accepting connection from {}".format(peer_name))
        self.protocol = protocol
        (self.ip, self.port) = peer_name

    @asyncio.coroutine
    def authenticate(self, session, player_id):
        """
        Perform very rudimentary authentication.

        For now, this exists primarily to avoid conditions with players,
        behind the same public address which would cause problems with the old design.
        """
        try:
            self.player = self.player_service[player_id]
            if self.player.session != session:
                self.log.info("Player attempted to authenticate with game connection with mismatched id/session pair.")
                self.abort()
                return

            self.log.debug("Resolved user to {} through lookup by {}:{}".format(self.player, self.ip, session))

            if self.player is None:
                self.log.info("Player not found for IP: %s " % self.ip)
                self.abort()
                return

            if self.player.game is None:
                self.log.info("Player hasn't indicated that he wants to join a game")
                self.abort()
                return

            self.game = self.player.game
            self.player.game_connection = self
            self.lobby = self.player.lobby_connection

            self.player.setPort = False
            self.player.connectedToHost = False

            self.ping_task = asyncio.async(self.ping())
            self._state = GameConnectionState.INITIALIZED
            self._authenticated.set_result(session)
        except (CancelledError, asyncio.InvalidStateError) as ex:
            self._logger.exception(ex)
            self.abort()

    def send_message(self, message):
        self.protocol.send_message(message)

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

    def _handle_idle_state(self):
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
                "%s.%s.%s\t" % (str(self.player.login), str(self.game.id), str(self.game.gamemod)))
            self.logGame = strlog
            self._send_create_lobby()

        elif state == PlayerState.JOINING:
            strlog = (
                "%s.%s.%s\t" % (str(self.player.login), str(self.game.id), str(self.game.gamemod)))
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
            with TestPeer(self,
                          self.player.ip,
                          self.player.game_port,
                          self.player.id) as peer_test:
                peer_status = yield from peer_test.determine_connectivity()
                self._connectivity_state.set_result(peer_status)
                self.send_gpgnet_message('ConnectivityState', [self.player.getId(),
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

    @asyncio.coroutine
    @timed(limit=0.1)
    def on_message_received(self, message):
        """
        Main entry point when reading messages
        :param message:
        :return:
        """
        try:
            message["command_id"] = message['action']
            message["arguments"] = message['chunks']
            yield from self.handle_action(message["action"], message["chunks"])
            self.notify(message)
        except ValueError as ex:  # pragma: no cover
            self.log.error("Garbage command {} {}".format(ex, message))

    def handle_ProcessServerNatPacket(self, arguments):
        self.log.debug("handle_ProcessServerNatPacket {}".format(self))
        self.notify({
            'command_id': 'ProcessServerNatPacket',
            'arguments': arguments
        })

    @asyncio.coroutine
    def ConnectToHost(self, peer):
        """
        Connect self to a given peer (host)
        :return:
        """
        assert peer.player.state == PlayerState.HOSTING
        connection, own_addr, peer_addr = yield from self.EstablishConnection(peer)
        if connection == ConnectivityState.PUBLIC or connection == ConnectivityState.STUN:
            self.send_JoinGame(peer_addr,
                               peer.player.login,
                               peer.player.id)
            peer.send_ConnectToPeer(own_addr,
                                    self.player.login,
                                    self.player.id)
        else:
            self.ConnectThroughProxy(peer)

    @asyncio.coroutine
    def ConnectToPeer(self, peer):
        """
        Connect two peers
        :return: None
        """
        connection, own_addr, peer_addr = yield from self.EstablishConnection(peer)
        if connection == ConnectivityState.PUBLIC or connection == ConnectivityState.STUN:
            self.send_ConnectToPeer(peer_addr,
                                    peer.player.login,
                                    peer.player.id)
            peer.send_ConnectToPeer(own_addr,
                                    self.player.login,
                                    self.player.id)
        else:
            self.ConnectThroughProxy(peer)

    @asyncio.coroutine
    def EstablishConnection(self, peer):
        """
        Attempt to establish a full duplex UDP connection
        between self and peer.

        :param peer: Client to connect to
        :return: (ConnectivityState, own_addr, remote_addr)
        """
        own_state = self._connectivity_state
        peer_state = peer._connectivity_state
        (done, pending) = yield from asyncio.wait([own_state, peer_state])
        if pending:
            self._logger.debug("Aborting due to lack of connectivity")
            self.abort()
        ((own_addr, own_state), (peer_addr, peer_state)) = own_state.result(), peer_state.result()
        if peer_state == ConnectivityState.PUBLIC and own_state == ConnectivityState.PUBLIC:
            self._logger.debug("Connecting {} to host {} directly".format(self, peer))
            return ConnectivityState.PUBLIC, own_addr, peer_addr
        elif peer_state == ConnectivityState.STUN or own_state == ConnectivityState.STUN:
            self._logger.debug("Connecting {} to host {} using STUN".format(self, peer))
            (own_addr, peer_addr) = yield from self.STUN(peer)
            if peer_addr is None or own_addr is None:
                self._logger.debug("STUN between {} {} failed".format(self, peer))
                self._logger.debug("Resolved addresses: {}, {}".format(peer_addr, own_addr))
                self._logger.debug("Own nat packets: {}".format(self.nat_packets))
                self._logger.debug("Peer nat packets: {}".format(peer.nat_packets))
            else:
                return ConnectivityState.STUN, own_addr, peer_addr
        self._logger.debug("Connecting {} to host {} through proxy".format(self, peer))
        return ConnectivityState.PROXY, None, None

    @asyncio.coroutine
    def STUN(self, peer):
        """
        Perform a STUN sequence between self and peer

        :param peer:
        :return: (own_addr, remote_addr) | None
        """
        own_addr = asyncio.async(self.ProbePeerNAT(peer))
        remote_addr = asyncio.async(peer.ProbePeerNAT(self))
        (done, pending) = yield from asyncio.wait([own_addr, remote_addr])
        assert len(pending) == 0
        assert len(done) == 2
        own_addr, remote_addr = own_addr.result(), remote_addr.result()
        if own_addr is not None and remote_addr is not None:
            # Both peers got it the first time
            return own_addr, remote_addr
        if own_addr is not None:
            # Remote received our packet, we didn't receive theirs
            # Instruct remote to try our new address
            remote_addr = yield from peer.ProbePeerNAT(self, use_address=own_addr)
        elif remote_addr is not None:
            # Opposite of the above
            own_addr = yield from self.ProbePeerNAT(peer, use_address=remote_addr)
        return own_addr, remote_addr

    @asyncio.coroutine
    def ProbePeerNAT(self, peer, use_address=None):
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
            received_message = asyncio.Future()
            peer.nat_packets[nat_message] = received_message
            yield from asyncio.wait_for(received_message, 4)
            return received_message.result()
        except (CancelledError, asyncio.TimeoutError):
            return None

    @asyncio.coroutine
    def handle_action(self, key, values):
        """
        Handle GpgNetSend messages, wrapped in the JSON protocol
        :param key: command type
        :param values: command parameters
        :type key str
        :type values list
        :return: None
        """
        try:
            if key == 'Authenticate':
                yield from self.authenticate(int(values[0]), int(values[1]))
            elif not self._authenticated.done():
                @asyncio.coroutine
                def queue_until_authed():
                    yield from self._authenticated
                    yield from self.handle_action(key, values)
                asyncio.async(queue_until_authed())
                return
            elif key == 'pong':
                self.last_pong = time.time()
                return

            elif key == 'ProcessNatPacket':
                address, message = values[0], values[1]
                self._logger.info("{}.ProcessNatPacket: {} {}".format(self, values[0], values[1]))
                if message in self.nat_packets and isinstance(self.nat_packets[message], asyncio.Future):
                    if not self.nat_packets[message].done():
                        self.nat_packets[message].set_result(address)

            elif key == 'Desync':
                self.game.desyncs += 1

            elif key == 'GameState':
                state = values[0]
                yield from self.handle_game_state(state)
                self._mark_dirty()

            elif key == 'GameOption':
                option_key = values[0]
                option_value = values[1]
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

            elif key == 'GameMods':
                if values[0] == "activated":
                    if values[1] == 0:
                        self.game.mods = {}

                if values[0] == "uids":
                    uids = values[1].split()
                    self.game.mods = {uid: "Unknown sim mod" for uid in uids}
                    with (yield from db.db_pool) as conn:
                        cursor = yield from conn.cursor()
                        yield from cursor.execute("SELECT uid, name from table_mod WHERE uid in %s", (uids, ))
                        mods = yield from cursor.fetchall()
                        for (uid, name) in mods:
                            self.game.mods[uid] = name
                self._mark_dirty()

            elif key == 'PlayerOption':
                if self.player.state == PlayerState.HOSTING:
                    id = values[0]
                    key = values[1]
                    value = values[2]
                    self.game.set_player_option(int(id), key, value)
                    self._mark_dirty()

            elif key == 'AIOption':
                if self.player.state == PlayerState.HOSTING:
                    name = values[0]
                    key = values[1]
                    value = values[2]
                    self.game.set_ai_option(str(name), key, value)
                    self._mark_dirty()

            elif key == 'ClearSlot':
                if self.player.state == PlayerState.HOSTING:
                    slot = values[0]
                    self.game.clear_slot(slot)
                self._mark_dirty()

            elif key == 'GameResult':
                army = int(values[0])
                result = str(values[1])
                try:
                    if not any(map(functools.partial(str.startswith, result),
                            ['score', 'default', 'victory', 'draw'])):
                        raise ValueError()  # pragma: no cover
                    result = result.split(' ')
                    self.game.add_result(self.player, army, result[0], int(result[1]))
                except (KeyError, ValueError):  # pragma: no cover
                    self.log.warn("Invalid result for {} reported: {}".format(army, result))
                    pass

            elif key == 'OperationComplete':
                if int(values[0]) == 1:
                    secondary, delta = int(values[1]), str(values[2])
                    with (yield from db.db_pool) as conn:
                        cursor = yield from conn.cursor()
                        # FIXME: Resolve used map earlier than this
                        yield from cursor.execute("SELECT id FROM coop_map WHERE filename LIKE '%/"
                                                  + self.game.map_file_path+".%'")
                        (mission, ) = yield from cursor.fetchone()
                        if not mission:
                            self._logger.debug("can't find coop map: {}".format(self.game.map_file_path))
                            return

                        yield from cursor.execute("INSERT INTO `coop_leaderboard`"
                                                  "(`mission`, `gameuid`, `secondary`, `time`) "
                                                  "VALUES (%s, %s, %s, %s);",
                                                  (mission, self.game.id, secondary, delta))

        except Exception as e:  # pragma: no cover
            self.log.exception(e)
            self.log.exception(self.logGame + "Something awful happened in a game thread!")
            self.abort()

    def on_ProcessNatPacket(self, address_and_port, message):
        self.nat_packets[message] = address_and_port

    @asyncio.coroutine
    def handle_game_state(self, state):
        """
        Changes in game state
        :param state: new state
        :return: None
        """
        if state == 'Idle':
            # FA has just connected to us
            self._handle_idle_state()

        elif state == 'Lobby':
            # The game is initialized and awaiting commands
            # At this point, it is listening locally on the
            # port we told it to (self.player.game_port)
            # We schedule an async task to determine their connectivity
            # and respond appropriately
            #
            # We do not yield from the task, since we
            # need to keep processing other commands while it runs
            asyncio.async(self._handle_lobby_state())

        elif state == 'Launching':
            if self.player.state == PlayerState.HOSTING:
                self.game.launch()

                if len(self.game.mods) > 0:
                    with (yield from db.db_pool) as conn:
                        cursor = yield from conn.cursor()
                        yield from cursor.execute("UPDATE `table_mod` SET `played`= `played`+1  WHERE uid in %s",
                                                  (self.game.mods.keys(), ))

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

    def ConnectThroughProxy(self, peer, recurse=True):
        try:
            n_proxy = self.game.proxy_map.map(self.player, peer.player)

            if n_proxy < 0:
                self.log.debug(self.logGame + "Maximum proxies used")  # pragma: no cover
                self.abort()

            self.game._logger.debug("%s is connecting through proxy to %s on port %i" % (
                self.player, peer.player, n_proxy))
            call = (n_proxy, peer.player.ip, str(peer.player.login), int(peer.player.id))
            self.log.debug(call)
            self.log.debug("Game host is {}".format(self.game.host))
            if peer.player == self.game.host:
                self.send_JoinProxy(*call)
            else:
                self.send_ConnectToProxy(*call)

            if recurse:
                peer.ConnectThroughProxy(self, False)
        except Exception as e:  # pragma: no cover
            self.log.exception(e)

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
                self.game.remove_game_connection(self)
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
            if self.state == GameConnectionState.CONNECTED_TO_HOST\
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
                       "to fix this.<br><br>The proxy server costs us a lot of bandwidth. It's free to use, but if you are using it often,<br>it would be nice to donate for the server maintenance costs,".format(wiki_link, wiki_link)

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
