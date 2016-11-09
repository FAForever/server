import asyncio
from collections import defaultdict
import time
import logging
import functools
from server.abc.base_game import GameConnectionState
from server.games.game import Game, GameState, Victory
from server.decorators import with_logger, timed
from server.game_service import GameService
from server.players import PlayerState, Player
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
                 game_service: GameService,
                 player: Player,
                 game: Game,
                 state: GameConnectionState=GameConnectionState.INITIALIZING):
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
        self._state = state
        self._waiters = defaultdict(list)
        self.loop = loop
        self.player_service = player_service
        self.game_service = game_service

        self.log = logging.getLogger(__name__)
        self.initTime = time.time()
        self.proxies = {}
        self._player = player
        self._game = game

        self.last_pong = time.time()

        self.ip, self.port = None, None
        self.lobby = None
        self._transport = None

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
        The game has told us it is ready for connections
        """
        try:
            player_state = self.player.state
            if player_state == PlayerState.HOSTING:
                self.send_HostGame(self.game.map_folder_name)
            # If the player is joining, we connect him to host
            # followed by the rest of the players.
            elif player_state == PlayerState.JOINING:
                await self.ConnectToHost(self.game.host.game_connection)
                self._state = GameConnectionState.CONNECTED_TO_HOST
                self.game.add_game_connection(self)
                for peer in self.game.connections:
                    if peer != self and peer.player != self.game.host:
                        self.log.debug("%s connecting to %s", self.player, peer)
                        asyncio.ensure_future(self.ConnectToPeer(peer))
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
        self.send_JoinGame(peer.player.login,
                           peer.player.id)
        peer.send_ConnectToPeer(self.player.login,
                                self.player.id)

    async def ConnectToPeer(self, peer):
        """
        Connect two peers
        :return: None
        """
        self.send_ConnectToPeer(peer.player.login,
                                peer.player.id)
        peer.send_ConnectToPeer(self.player.login,
                                self.player.id)

    async def handle_action(self, command, args):
        """
        Handle GpgNetSend messages, wrapped in the JSON protocol
        :param command: command type
        :param arguments: command arguments
        :return: None
        """
        try:
            if command == 'Desync':
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
                    self.game.map_scenario_path = raw.replace('\\', '/').\
                                                  replace('//', '/').\
                                                  replace("'", '')
                    self.game.map_file_path = 'maps/{}.zip'.format(self.game.map_scenario_path.split('/')[2])
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
                    if not len(args) == 3:
                        self._logger.exception("Malformed playeroption args: %s", args)
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
                    self.log.warn("Invalid result for %s reported: %s", army, result)
                    pass

            elif command == 'OperationComplete':
                if int(args[0]) == 1:
                    secondary, delta = int(args[1]), str(args[2])
                    async with db.db_pool.get() as conn:
                        cursor = await conn.cursor()
                        # FIXME: Resolve used map earlier than this
                        await cursor.execute("SELECT id FROM coop_map WHERE filename LIKE '%/"
                                             + self.game.map_file_path + ".%'")
                        (mission,) = await cursor.fetchone()
                        if not mission:
                            self._logger.debug("can't find coop map: %s", self.game.map_file_path)
                            return

                        await cursor.execute("INSERT INTO `coop_leaderboard`"
                                             "(`mission`, `gameuid`, `secondary`, `time`) "
                                             "VALUES (%s, %s, %s, %s);",
                                             (mission, self.game.id, secondary, delta))
            elif command == 'JsonStats':
                await self.game.report_army_stats(args[0])

            elif command == 'EnforceRating':
                self.game.enforce_rating = True

            elif command == 'TeamkillReport':
                # args[0] -> seconds of gametime when kill happened
                # args[1] -> victim id
                # args[2] -> victim nickname (for debug purpose only)
                # args[3] -> teamkiller id
                # args[3] -> teamkiller nickname (for debug purpose only)
                gametime, victim_id, victim_name, teamkiller_id, teamkiller_name = args

                async with db.db_pool.get() as conn:
                    cursor = await conn.cursor()

                    await cursor.execute("INSERT INTO `teamkills`"
                                         "(`teamkiller`, `victim`, `game_id`, `gametime`) "
                                         "VALUES (%s, %s, %s, %s);",
                                         (teamkiller_id, victim_id, self.game.id, gametime))

            elif command == 'SdpRecord':
                receiver_id = int(args[0])
                sdp_record = args[1]

                peer = self.player_service.get_player(receiver_id)
                if not peer:
                    self._logger.info("Ignoring SDP record for unknown player: %s", receiver_id)
                    return

                game_connection = peer.game_connection
                if not game_connection:
                    self._logger.info("Ignoring SDP for player without game connection: %s", receiver_id)
                    return

                game_connection.send_message(dict(command="SdpRecord", args=[int(self.player.id), sdp_record]))

        except AuthenticationError as e:
            self.log.exception("Authentication error: %s", e)
            self.abort()
        except Exception as e:  # pragma: no cover
            self.log.exception(e)
            self.log.exception("Something awful happened in a game thread!")
            self.abort()

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
            #
            # We do not yield from the task, since we
            # need to keep processing other commands while it runs
            asyncio.ensure_future(self._handle_lobby_state())

        elif state == 'Launching':
            if self.player.state == PlayerState.HOSTING:
                await self.game.launch()

                if len(self.game.mods.keys()) > 0:
                    async with db.db_pool.get() as conn:
                        cursor = await conn.cursor()
                        uids = list(self.game.mods.keys())
                        await cursor.execute("UPDATE mod_stats s "
                                             "JOIN mod_version v ON v.mod_id = s.mod_id "
                                             "SET s.times_played = s.times_played + 1 WHERE v.uid in %s", (uids,))
        elif state == 'Ended':
            await self.on_connection_lost()

    def _mark_dirty(self):
        if self.game:
            self.game_service.mark_dirty(self.game)

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
                        except Exception as ex: # pragma no cover
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

    def __str__(self):
        return "GameConnection(Player({}),Game({}))".format(self.player, self.game)
