import asyncio
from collections import defaultdict
import time
import logging
import functools
from server.abc.base_game import GameConnectionState
from server.connectivity import ConnectivityState
from server.games.game import GameState, Victory
from server.decorators import with_logger, timed
from server.game_service import GameService
from server.players import PlayerState
from server.protocol import GpgNetServerProtocol
import server.db as db

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    pass


@with_logger
class GameConnection(GpgNetServerProtocol):
    """
    Responsible for connections to the game, using the GPGNet protocol
    """

    def __init__(self, loop: asyncio.BaseEventLoop,
                 lobby_connection: "LobbyConnection",
                 player_service: "PlayerService",
                 games: GameService):
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
        self._logger.debug('GameConnection initializing')
        self._state = GameConnectionState.INITIALIZING
        self._waiters = defaultdict(list)
        self.loop = loop
        self.player_service = player_service
        self.games = games

        self.log = logging.getLogger(__name__)
        self.initTime = time.time()
        self.proxies = {}
        self._player = None
        self._game = None

        self.last_pong = time.time()

        self.ip, self.port = None, None
        self.lobby = None
        self._transport = None

        self.connectivity = self.lobby_connection.connectivity  # type: Connectivity

        self.finished_sim = False

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

    async def _handle_idle_state(self):
        """
        This message is sent by FA when it doesn't know what to do.
        :return: None
        """
        assert self.game
        state = self.player.state

        if state == PlayerState.HOSTING:
            self.game.state = GameState.LOBBY
            self._state = GameConnectionState.CONNECTED_TO_HOST
            self.game.add_game_connection(self)
            self.game.host = self.player
        elif state == PlayerState.JOINING:
            pass
        else:
            self.log.exception("Unknown PlayerState")
            self.abort()

    async def _handle_lobby_state(self):
        """
        The game has told us it is ready and listening on
        self.player.game_port for UDP.
        We determine the connectivity of the peer and respond
        appropriately
        """
        try:
            player_state = self.player.state
            if player_state == PlayerState.HOSTING:
                self.send_HostGame(self.game.map_folder_name)
            # If the player is joining, we connect him to host
            # followed by the rest of the players.
            elif player_state == PlayerState.JOINING:
                await self.ConnectToHost(self.game.host.game_connection)
                if self._state is GameConnectionState.ENDED:  # We aborted while trying to connect
                    return

                self._state = GameConnectionState.CONNECTED_TO_HOST
                self.game.add_game_connection(self)
                for peer in self.game.connections:
                    if peer != self and peer.player != self.game.host:
                        self.log.debug("%s connecting to %s", self.player, peer)
                        asyncio.ensure_future(self.ConnectToPeer(peer))
        except Exception as e:  # pragma: no cover
            self.log.exception(e)

    @timed(limit=0.1)
    async def on_message_received(self, message):
        """
        Main entry point when reading messages
        :param message:
        :return:
        """
        try:
            cmd_id, args = message['command'], message['args']
            await self.handle_action(cmd_id, args)
            if cmd_id in self._waiters:
                for waiter in self._waiters[cmd_id]:
                    waiter.set_result(message)
                    self._waiters[cmd_id].remove(waiter)
        except ValueError as ex:  # pragma: no cover
            self.log.error("Garbage command %s %s", ex, message)

    async def ConnectToHost(self, peer):
        """
        Connect self to a given peer (host)
        :return:
        """
        assert peer.player.state == PlayerState.HOSTING
        result = await self.EstablishConnection(peer)
        if not result:
            self.abort("Failed connecting to host {}".format(peer))
        own_addr, peer_addr = result
        self.send_JoinGame(peer_addr,
                           peer.player.login,
                           peer.player.id)
        peer.send_ConnectToPeer(own_addr,
                                self.player.login,
                                self.player.id)

    async def ConnectToPeer(self, peer):
        """
        Connect two peers
        :return: None
        """
        result = await self.EstablishConnection(peer)
        if not result:
            self.abort("Failed connecting to {}".format(peer))
        own_addr, peer_addr = result
        self.send_ConnectToPeer(peer_addr,
                                peer.player.login,
                                peer.player.id)
        peer.send_ConnectToPeer(own_addr,
                                self.player.login,
                                self.player.id)

    async def EstablishConnection(self, peer_connection: "GameConnection"):
        """
        Attempt to establish a full duplex UDP connection
        between self and peer.

        :param peer_connection: Client to connect to
        :return: (own_addr, remote_addr)
        """
        own = self.connectivity.result  # type: ConnectivityResult
        peer = peer_connection.connectivity.result  # type: ConnectivityResult
        if peer.state == ConnectivityState.PUBLIC \
                and own.state == ConnectivityState.PUBLIC:
            self._logger.debug("Connecting %s to host %s directly", self, peer_connection)
            return own.addr, peer.addr
        elif peer.state == ConnectivityState.STUN or own.state == ConnectivityState.STUN:
            self._logger.debug("Connecting %s to host %s using STUN", self, peer_connection)
            (own_addr, peer_addr) = await self.STUN(peer_connection)
            if peer_addr is None or own_addr is None:
                self._logger.debug("STUN between %s %s failed", self, peer_connection)
                self._logger.debug("Resolved addresses: %s, %s", peer_addr, own_addr)
                if self.player.id < peer_connection.player.id and own.state == ConnectivityState.STUN:
                    return await self.TURN(peer_connection)
                elif peer.state == ConnectivityState.STUN:
                    return tuple(reversed(await peer_connection.TURN(self)))
            else:
                return own_addr, peer_addr
        self._logger.error("Connection blocked")

    async def TURN(self, peer: 'GameConnection'):
        addr = await self.connectivity.create_binding(peer.connectivity)
        return self.lobby_connection.connectivity.relay_address, addr

    async def STUN(self, peer):
        """
        Perform a STUN sequence between self and peer

        :param peer:
        :return: (own_addr, remote_addr) | None
        """
        own_addr = asyncio.ensure_future(self.connectivity.ProbePeerNAT(peer))
        remote_addr = asyncio.ensure_future(peer.connectivity.ProbePeerNAT(self))
        (done, pending) = await asyncio.wait([own_addr, remote_addr], return_when=asyncio.FIRST_COMPLETED)
        if own_addr.done() and remote_addr.done() and not own_addr.cancelled() and not remote_addr.cancelled():
            # Both peers got it the first time
            return own_addr.result(), remote_addr.result()
        if own_addr.done() and not own_addr.cancelled():
            # Remote received our packet, we didn't receive theirs
            # Instruct remote to try our new address
            own_addr = own_addr.result()
            remote_addr = await peer.connectivity.ProbePeerNAT(self, use_address=own_addr)
        elif remote_addr.done() and not remote_addr.cancelled():
            # Opposite of the above
            remote_addr = remote_addr.result()
            own_addr = await self.connectivity.ProbePeerNAT(peer, use_address=remote_addr)
        for p in pending:
            if not p.done():
                p.cancel()
        return own_addr, remote_addr

    async def handle_action(self, command, args):
        """
        Handle GpgNetSend messages, wrapped in the JSON protocol
        :param command: command type
        :param args: command arguments
        :return: None
        """

        try:
            await COMMAND_HANDLERS[command](self, *args)
        except KeyError:
            self._logger.exception("Unrecognized command %s: %s from player %s",
                                   command, args, self.player)
        except (TypeError, ValueError) as e:
            self._logger.exception("Bad command arguments: %s", e)
        except AuthenticationError as e:
            self.log.exception("Authentication error: %s", e)
            self.abort()
        except Exception as e:  # pragma: no cover
            self.log.exception(e)
            self.log.exception("Something awful happened in a game thread!")
            self.abort()

    async def handle_desync(self):  # pragma: no cover
        self.game.desyncs += 1

    async def handle_game_option(self, key, value):
        if key == 'Victory':
            self.game.gameOptions['Victory'] = Victory.from_gpgnet_string(value)
        elif key in self.game.gameOptions:

            """
            This block about AIReplacement is added because of a mistake in the FAF game patch code
            that makes "On" and "Off" be "AIReplacementOn" and "AIReplacementOff". The code
            below removes that extra statement to make it a simple "On" "Off".
            This block can be removed as soon as the game sends "On" and "Off" instead of
            "AIReplacementOn" and "AIReplacementOff" to the server as game options.
            https://github.com/FAForever/fa/issues/2610
            """
            if key == "AIReplacement":
                value = value.replace("AIReplacement", "")

            self.game.gameOptions[key] = value

        if key == "Slots":
            self.game.max_players = int(value)
        elif key == 'ScenarioFile':
            raw = "%r" % value
            self.game.map_scenario_path = \
                raw.replace('\\', '/').replace('//', '/').replace("'", '')
            self.game.map_file_path = 'maps/{}.zip'.format(
                self.game.map_scenario_path.split('/')[2].lower()
            )
        elif key == 'Title':
            self.game.name = self.game.sanitize_name(value)

        self._mark_dirty()

    async def handle_game_mods(self, mode, args):
        if mode == "activated":
            # In this case args is the number of mods
            if int(args) == 0:
                self.game.mods = {}

        elif mode == "uids":
            uids = args.split()
            self.game.mods = {uid: "Unknown sim mod" for uid in uids}
            async with db.db_pool.get() as conn:
                cursor = await conn.cursor()
                await cursor.execute("SELECT uid, name from table_mod WHERE uid in %s", (uids,))
                mods = await cursor.fetchall()
                for (uid, name) in mods:
                    self.game.mods[uid] = name
        self._mark_dirty()

    async def handle_player_option(self, id_, command, value):
        if self.player.state != PlayerState.HOSTING:
            return

        self.game.set_player_option(int(id_), command, value)
        self._mark_dirty()

    async def handle_ai_option(self, name, key, value):
        if self.player.state != PlayerState.HOSTING:
            return

        self.game.set_ai_option(str(name), key, value)
        self._mark_dirty()

    async def handle_clear_slot(self, slot):
        if self.player.state != PlayerState.HOSTING:
            return

        self.game.clear_slot(int(slot))
        self._mark_dirty()

    async def handle_game_result(self, army, result):
        army = int(army)
        result = str(result)
        try:
            if not any(map(functools.partial(str.startswith, result),
                           ['score', 'defeat', 'victory', 'draw'])):
                raise ValueError()  # pragma: no cover
            result = result.split(' ')

            # This is the most common way for the player's sim to end
            # We should add a reliable message to lua in the future
            if result[0] in ['victory', 'draw'] and not self.finished_sim:
                self.finished_sim = True
                await self.game.check_sim_end()

            await self.game.add_result(self.player, army, result[0], int(result[1]))
        except (KeyError, ValueError):  # pragma: no cover
            self.log.warning("Invalid result for %s reported: %s", army, result)

    async def handle_operation_complete(self, army, secondary, delta):
        if not int(army) == 1:
            return

        secondary, delta = int(secondary), str(delta)
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()
            # FIXME: Resolve used map earlier than this
            await cursor.execute("SELECT id FROM coop_map WHERE filename = %s",
                                 self.game.map_file_path)
            row = await cursor.fetchone()
            if not row:
                self._logger.debug("can't find coop map: %s", self.game.map_file_path)
                return
            (mission,) = row

            await cursor.execute(
                """ INSERT INTO `coop_leaderboard`
                    (`mission`, `gameuid`, `secondary`, `time`, `player_count`)
                    VALUES (%s, %s, %s, %s, %s)""",
                (mission, self.game.id, secondary, delta, len(self.game.players))
            )

    async def handle_json_stats(self, stats):
        await self.game.report_army_stats(stats)

    async def handle_enforce_rating(self):
        self.game.enforce_rating = True

    async def handle_teamkill_report(self, gametime, victim_id, victim_name, teamkiller_id, teamkiller_name):
        """
            :param gametime: seconds of gametime when kill happened
            :param victim_id: victim id
            :param victim_name: victim nickname (for debug purpose only)
            :param teamkiller_id: teamkiller id
            :param teamkiller_name: teamkiller nickname (for debug purpose only)
        """

        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            await cursor.execute(
                """ INSERT INTO `teamkills` (`teamkiller`, `victim`, `game_id`, `gametime`)
                    VALUES (%s, %s, %s, %s)""",
                (teamkiller_id, victim_id, self.game.id, gametime)
            )

    async def handle_game_state(self, state):
        """
        Changes in game state
        :param state: new state
        :return: None
        """
        if state == 'Idle':
            await self._handle_idle_state()

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
            if self.player.state != PlayerState.HOSTING:
                return

            await self.game.launch()

            if len(self.game.mods.keys()) > 0:
                async with db.db_pool.get() as conn:
                    cursor = await conn.cursor()
                    uids = list(self.game.mods.keys())
                    await cursor.execute(
                        """ UPDATE mod_stats s JOIN mod_version v ON v.mod_id = s.mod_id
                            SET s.times_played = s.times_played + 1 WHERE v.uid in %s""",
                        (uids,)
                    )
        elif state == 'Ended':
            await self.on_connection_lost()

        self._mark_dirty()

    def _mark_dirty(self):
        if self.game:
            self.games.mark_dirty(self.game)

    def abort(self, logspam=''):
        """
        Abort the connection

        Removes the GameConnection object from the any associated Game object,
        and deletes references to Player and Game held by this object.
        """
        try:
            if self._state is GameConnectionState.ENDED:
                return
            if self.game.state == GameState.LOBBY:
                for peer in self.game.connections:
                    if peer != self:
                        try:
                            peer.send_DisconnectFromPeer(self.player.id)
                        except Exception as ex:  # pragma no cover
                            self.log.exception("peer_sendDisconnectFromPeer failed for player %i", self.player.id)
            self._state = GameConnectionState.ENDED
            self.loop.create_task(self.game.remove_game_connection(self))
            self._mark_dirty()
            self.log.debug("%s.abort(%s)", self, logspam)
            self.player.state = PlayerState.IDLE
            del self.player.game
            del self.player.game_connection
        except Exception as ex:  # pragma: no cover
            self.log.debug("Exception in abort(): %s", ex)
        finally:
            self.lobby_connection.game_connection = None

    async def on_connection_lost(self):
        try:
            await self.game.remove_game_connection(self)
        except Exception as e:  # pragma: no cover
            self._logger.exception(e)
        finally:
            self.abort()

    def address_and_port(self):
        return "{}:{}".format(self.player.ip, self.player.game_port)

    def __str__(self):
        return "GameConnection(Player({}),Game({}))".format(self.player, self.game)


COMMAND_HANDLERS = {
    "Desync":               GameConnection.handle_desync,
    "GameState":            GameConnection.handle_game_state,
    "GameOption":           GameConnection.handle_game_option,
    "GameMods":             GameConnection.handle_game_mods,
    "PlayerOption":         GameConnection.handle_player_option,
    "AIOption":             GameConnection.handle_ai_option,
    "ClearSlot":            GameConnection.handle_clear_slot,
    "GameResult":           GameConnection.handle_game_result,
    "OperationComplete":    GameConnection.handle_operation_complete,
    "JsonStats":            GameConnection.handle_json_stats,
    "EnforceRating":        GameConnection.handle_enforce_rating,
    "TeamkillReport":       GameConnection.handle_teamkill_report
}
