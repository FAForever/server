"""
Game communication over GpgNet
"""

import asyncio
import contextlib
import json
from typing import Any

from sqlalchemy import select

from server.db import FAFDatabase

from .config import TRACE
from .db.models import coop_leaderboard, coop_map, teamkills
from .decorators import with_logger
from .game_service import GameService
from .games import (
    CoopGame,
    Game,
    GameConnectionState,
    GameError,
    GameState,
    ValidityState,
    Victory
)
from .games.typedefs import FA
from .player_service import PlayerService
from .players import Player, PlayerState
from .protocol import DisconnectedError, GpgNetServerProtocol, Protocol


@with_logger
class GameConnection(GpgNetServerProtocol):
    """
    Responsible for connections to the game, using the GPGNet protocol
    """

    def __init__(
        self,
        database: FAFDatabase,
        game: Game,
        player: Player,
        protocol: Protocol,
        player_service: PlayerService,
        games: GameService,
        state: GameConnectionState = GameConnectionState.INITIALIZING
    ):
        """
        Construct a new GameConnection
        """
        super().__init__()
        self._db = database
        self._logger.debug("GameConnection initializing")

        self.protocol = protocol
        self._state = state
        self.game_service = games
        self.player_service = player_service

        self._player = player
        player.game_connection = self  # Set up weak reference to self
        self._game = game

        self.finished_sim = False

    @property
    def state(self) -> GameConnectionState:
        return self._state

    @property
    def game(self) -> Game:
        return self._game

    @game.setter
    def game(self, val: Game):
        self._game = val

    @property
    def player(self) -> Player:
        return self._player

    @player.setter
    def player(self, val: Player):
        self._player = val

    def is_host(self) -> bool:
        if not self.game or not self.player:
            return False

        return (
            self.player.state == PlayerState.HOSTING and
            self.player == self.game.host
        )

    async def send(self, message):
        """
        Send a game message to the client.

        # Errors
        May raise `DisconnectedError`

        NOTE: When calling this on a connection other than `self` make sure to
        handle `DisconnectedError`, otherwise failure to send the message will
        cause the caller to be disconnected as well.
        """
        message["target"] = "game"

        self._logger.log(TRACE, ">> %s: %s", self.player.login, message)
        await self.protocol.send_message(message)

    async def _handle_idle_state(self):
        """
        This message is sent by FA when it doesn't know what to do.
        """
        assert self.game

        if self.player == self.game.host:
            self.game.state = GameState.LOBBY
            self._state = GameConnectionState.CONNECTED_TO_HOST
            self.game.add_game_connection(self)
            self.player.state = PlayerState.HOSTING
        else:
            self.player.state = PlayerState.JOINING

    async def _handle_lobby_state(self):
        """
        The game has told us it is ready and listening on
        self.player.game_port for UDP.
        We determine the connectivity of the peer and respond
        appropriately
        """
        player_state = self.player.state
        if player_state == PlayerState.HOSTING:
            await self.send_HostGame(self.game.map_folder_name)
            self.game.set_hosted()
        # If the player is joining, we connect him to host
        # followed by the rest of the players.
        elif player_state == PlayerState.JOINING:
            await self.connect_to_host(self.game.host.game_connection)

            if self._state is GameConnectionState.ENDED:
                # We aborted while trying to connect
                return

            self._state = GameConnectionState.CONNECTED_TO_HOST

            try:
                self.game.add_game_connection(self)
            except GameError as e:
                await self.abort(f"GameError while joining {self.game.id}: {e}")
                return

            tasks = []
            for peer in self.game.connections:
                if peer != self and peer.player != self.game.host:
                    self._logger.debug("%s connecting to %s", self.player, peer)
                    tasks.append(self.connect_to_peer(peer))
            await asyncio.gather(*tasks)

    async def connect_to_host(self, peer: "GameConnection"):
        """
        Connect self to a given peer (host)
        """
        if not peer or peer.player.state != PlayerState.HOSTING:
            await self.abort("The host left the lobby")
            return

        await self.send_JoinGame(peer.player.login, peer.player.id)

        if not peer:
            await self.abort("The host left the lobby")
            return

        await peer.send_ConnectToPeer(
            player_name=self.player.login,
            player_uid=self.player.id,
            offer=True
        )

    async def connect_to_peer(self, peer: "GameConnection"):
        """
        Connect two peers
        """
        if peer is not None:
            await self.send_ConnectToPeer(
                player_name=peer.player.login,
                player_uid=peer.player.id,
                offer=True
            )

        if peer is not None:
            with contextlib.suppress(DisconnectedError):
                await peer.send_ConnectToPeer(
                    player_name=self.player.login,
                    player_uid=self.player.id,
                    offer=False
                )

    async def handle_action(self, command: str, args: list[Any]):
        """
        Handle GpgNetSend messages, wrapped in the JSON protocol
        """
        try:
            await COMMAND_HANDLERS[command](self, *args)
        except KeyError:
            self._logger.warning(
                "Unrecognized command %s: %s from player %s",
                command, args, self.player
            )
        except (TypeError, ValueError):
            self._logger.exception("Bad command arguments")
        except ConnectionError as e:
            raise e
        except Exception:  # pragma: no cover
            self._logger.exception("Something awful happened in a game thread!")
            await self.abort()

    async def handle_desync(self, *_args):  # pragma: no cover
        self.game.desyncs += 1

    async def handle_game_option(self, key: str, value: Any):
        if not self.is_host():
            return

        if key == "Victory":
            self.game.gameOptions["Victory"] = Victory.__members__.get(
                value.upper(), None
            )
        else:
            self.game.gameOptions[key] = value

        if key == "Slots":
            self.game.max_players = int(value)
        elif key == "ScenarioFile":
            raw = repr(value)
            self.game.map_scenario_path = \
                raw.replace("\\", "/").replace("//", "/").replace("'", "")
            self.game.map_file_path = "maps/{}.zip".format(
                self.game.map_scenario_path.split("/")[2].lower()
            )
        elif key == "Title":
            with contextlib.suppress(ValueError):
                self.game.name = value

        self._mark_dirty()

    async def handle_game_mods(self, mode: Any, args: list[Any]):
        if not self.is_host():
            return

        if mode == "activated":
            # In this case args is the number of mods
            if int(args) == 0:
                self.game.mods = {}

        elif mode == "uids":
            uids = str(args).split()
            self.game.mods = {uid: "Unknown sim mod" for uid in uids}
            async with self._db.acquire() as conn:
                rows = await conn.execute(
                    "SELECT `uid`, `name` from `table_mod` WHERE `uid` in :ids",
                    ids=tuple(uids)
                )
                for row in rows:
                    self.game.mods[row.uid] = row.name
        else:
            self._logger.warning("Ignoring game mod: %s, %s", mode, args)
            return

        self._mark_dirty()

    async def handle_player_option(
        self, player_id: Any, key: Any, value: Any
    ):
        if not self.is_host():
            return

        self.game.set_player_option(int(player_id), key, value)
        self._mark_dirty()

    async def handle_ai_option(self, name: Any, key: Any, value: Any):
        if not self.is_host():
            return

        self.game.set_ai_option(str(name), key, value)
        self._mark_dirty()

    async def handle_clear_slot(self, slot: Any):
        if not self.is_host():
            return

        self.game.clear_slot(int(slot))
        self._mark_dirty()

    async def handle_game_result(self, army: Any, result: Any):
        army = int(army)
        result = str(result).lower()

        try:
            *metadata, result_type, score = result.split()
        except ValueError:
            self._logger.warning("Invalid result for %s reported: %s", army, result)
        else:
            await self.game.add_result(
                self.player.id, army, result_type, int(score), frozenset(metadata)
            )

    async def handle_operation_complete(
        self, primary: Any, secondary: Any, delta: str
    ):
        """
        # Params
        - `primary`: are primary mission objectives complete?
        - `secondary`: are secondary mission objectives complete?
        - `delta`: the time it took to complete the mission
        """
        primary = FA.ENABLED == primary
        secondary = FA.ENABLED == secondary

        if not primary:
            return

        if not isinstance(self.game, CoopGame):
            self._logger.warning(
                "OperationComplete called for non-coop game: %s", self.game.id
            )
            return

        if self.game.validity != ValidityState.COOP_NOT_RANKED:
            return

        secondary, delta = secondary, str(delta)
        async with self._db.acquire() as conn:
            result = await conn.execute(
                select([coop_map.c.id]).where(
                    coop_map.c.filename == self.game.map_file_path
                )
            )
            row = result.fetchone()
            if not row:
                self._logger.debug(
                    "can't find coop map: %s", self.game.map_file_path
                )
                return
            mission = row.id

            # Each player in a co-op game will send the OperationComplete
            # message but we only need to perform this insert once
            if not self.game.leaderboard_saved:
                await conn.execute(
                    coop_leaderboard.insert().values(
                        mission=mission,
                        gameuid=self.game.id,
                        secondary=secondary,
                        time=delta,
                        player_count=len(self.game.players),
                    )
                )
                self.game.leaderboard_saved = True

    async def handle_json_stats(self, stats: str):
        try:
            self.game.report_army_stats(stats)
        except json.JSONDecodeError:
            self._logger.warning(
                "Malformed game stats reported by %s: '...%s'",
                self._player.login,
                stats[-20:]
            )

    async def handle_enforce_rating(self):
        self.game.enforce_rating = True

    async def handle_teamkill_report(
        self,
        gametime: Any,
        reporter_id: Any,
        reporter_name: str,
        teamkiller_id: Any,
        teamkiller_name: str,
    ):
        """
        Sent when a player is teamkilled and clicks the 'Report' button.

        # Params
        - `gametime`: seconds of gametime when kill happened
        - `reporter_id`: reporter id
        - `reporter_name`: reporter nickname (for debug purpose only)
        - `teamkiller_id`: teamkiller id
        - `teamkiller_name`: teamkiller nickname (for debug purpose only)
        """
        pass

    async def handle_teamkill_happened(
        self,
        gametime: Any,
        victim_id: Any,
        victim_name: str,
        teamkiller_id: Any,
        teamkiller_name: str,
    ):
        """
        Send automatically by the game whenever a teamkill happens. Takes
        the same parameters as TeamkillReport.

        # Params
        - `gametime`: seconds of gametime when kill happened
        - `victim_id`: victim id
        - `victim_name`: victim nickname (for debug purpose only)
        - `teamkiller_id`: teamkiller id
        - `teamkiller_name`: teamkiller nickname (for debug purpose only)
        """
        victim_id = int(victim_id)
        teamkiller_id = int(teamkiller_id)

        if 0 in (victim_id, teamkiller_id):
            self._logger.debug("Ignoring teamkill for AI player")
            return

        async with self._db.acquire() as conn:
            await conn.execute(
                teamkills.insert().values(
                    teamkiller=teamkiller_id,
                    victim=victim_id,
                    game_id=self.game.id,
                    gametime=gametime,
                )
            )

    async def handle_ice_message(self, receiver_id: Any, ice_msg: str):
        receiver_id = int(receiver_id)
        peer = self.player_service.get_player(receiver_id)
        if not peer:
            self._logger.debug(
                "Ignoring ICE message for unknown player: %s", receiver_id
            )
            return

        game_connection = peer.game_connection
        if not game_connection:
            self._logger.debug(
                "Ignoring ICE message for player without game connection: %s", receiver_id
            )
            return

        try:
            await game_connection.send({
                "command": "IceMsg",
                "args": [int(self.player.id), ice_msg]
            })
        except DisconnectedError:
            self._logger.debug(
                "Failed to send ICE message to player due to a disconnect: %s",
                receiver_id
            )

    async def handle_game_state(self, state: str):
        """
        Changes in game state
        """

        if state == "Idle":
            await self._handle_idle_state()
            # Don't mark as dirty
            return

        elif state == "Lobby":
            # TODO: Do we still need to schedule with `ensure_future`?
            #
            # We do not yield from the task, since we
            # need to keep processing other commands while it runs
            await self._handle_lobby_state()

        elif state == "Launching":
            if self.player.state != PlayerState.HOSTING:
                return

            if self.game.state is not GameState.LOBBY:
                self._logger.warning(
                    "Trying to launch game %s in invalid state %s",
                    self.game,
                    self.game.state
                )
                return

            self._logger.info("Launching game %s", self.game)

            await self.game.launch()

            if len(self.game.mods.keys()) > 0:
                async with self._db.acquire() as conn:
                    uids = list(self.game.mods.keys())
                    await conn.execute(
                        "UPDATE mod_stats s JOIN mod_version v ON "
                        "v.mod_id = s.mod_id "
                        "SET s.times_played = s.times_played + 1 "
                        "WHERE v.uid in :ids",
                        ids=tuple(uids)
                    )
        elif state == "Ended":
            """
            Signals that the FA executable has been closed
            """
            await self.on_connection_lost()
        self._mark_dirty()

    async def handle_game_ended(self, *args:  list[Any]):
        """
        Signals that the simulation has ended.
        """
        self.finished_sim = True
        await self.game.check_sim_end()

        # FIXME Move this into check_sim_end
        if self.game.finished:
            await self.game.on_game_finish()

    async def handle_rehost(self, *args: list[Any]):
        """
        Signals that the user has rehosted the game. This is currently unused but
        included for documentation purposes.
        """
        pass

    async def handle_bottleneck(self, *args: list[Any]):
        """
        Not sure what this command means. This is currently unused but
        included for documentation purposes.
        """
        pass

    async def handle_bottleneck_cleared(self, *args: list[Any]):
        """
        Not sure what this command means. This is currently unused but
        included for documentation purposes.
        """
        pass

    async def handle_disconnected(self, *args: list[Any]):
        """
        Not sure what this command means. This is currently unused but
        included for documentation purposes.
        """
        pass

    async def handle_chat(self, message: str):
        """
        Whenever the player sends a chat message during the game lobby.
        """
        pass

    async def handle_game_full(self):
        """
        Sent when all game slots are full
        """
        pass

    def _mark_dirty(self):
        if self.game:
            self.game_service.mark_dirty(self.game)

    async def abort(self, log_message: str = ""):
        """
        Abort the connection

        Removes the GameConnection object from the any associated Game object,
        and deletes references to Player and Game held by this object.
        """
        try:
            if self._state is GameConnectionState.ENDED:
                return

            self._logger.debug("%s.abort(%s)", self, log_message)

            if self.game.state is GameState.LOBBY:
                await self.disconnect_all_peers()

            self._state = GameConnectionState.ENDED
            await self.game.remove_game_connection(self)
            self._mark_dirty()
            self.player.state = PlayerState.IDLE
            if self.player.lobby_connection:
                self.player.lobby_connection.game_connection = None
            del self.player.game
            del self.player.game_connection
        except Exception as ex:  # pragma: no cover
            self._logger.debug("Exception in abort(): %s", ex)

    async def disconnect_all_peers(self):
        tasks = []
        for peer in self.game.connections:
            if peer == self:
                continue

            tasks.append(peer.send_DisconnectFromPeer(self.player.id))

        for fut in asyncio.as_completed(tasks):
            try:
                await fut
            except Exception:
                self._logger.debug(
                    "peer_sendDisconnectFromPeer failed for player %i",
                    self.player.id,
                    exc_info=True
                )

    async def on_connection_lost(self):
        try:
            await self.game.remove_game_connection(self)
        except Exception as e:  # pragma: no cover
            self._logger.exception(e)
        finally:
            await self.abort()

    def __str__(self):
        return f"GameConnection({self.player}, {self.game})"


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
    "TeamkillReport":       GameConnection.handle_teamkill_report,
    "TeamkillHappened":     GameConnection.handle_teamkill_happened,
    "GameEnded":            GameConnection.handle_game_ended,
    "Rehost":               GameConnection.handle_rehost,
    "Bottleneck":           GameConnection.handle_bottleneck,
    "BottleneckCleared":    GameConnection.handle_bottleneck_cleared,
    "Disconnected":         GameConnection.handle_disconnected,
    "IceMsg":               GameConnection.handle_ice_message,
    "Chat":                 GameConnection.handle_chat,
    "GameFull":             GameConnection.handle_game_full
}
