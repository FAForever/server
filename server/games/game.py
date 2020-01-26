import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import pymysql
from server.config import FFA_TEAM
from server.db.models import game_player_stats, game_stats
from server.games.game_results import (
    GameOutcome, GameResolutionError, GameResultReport, GameResultReports,
    resolve_game
)
from server.rating import RatingType
from sqlalchemy import and_, bindparam
from sqlalchemy.sql.functions import now as sql_now

from ..abc.base_game import GameConnectionState, InitMode
from ..players import Player, PlayerState
from .typedefs import (
    BasicGameInfo, EndedGameInfo, GameState, ValidityState, Victory,
    VisibilityState
)


class GameError(Exception):
    pass


class Game:
    """
    Object that lasts for the lifetime of a game on FAF.
    """
    """
    The initialization mode to use for the Game.
    """
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(
        self,
        id_: int,
        database: "FAFDatabase",
        game_service: "GameService",
        game_stats_service: "GameStatsService",
        host: Optional[Player] = None,
        name: str = 'None',
        map_: str = 'SCMP_007',
        game_mode: str = 'faf',
        rating_type: Optional[RatingType] = None,
    ):
        self._db = database
        self._results = GameResultReports(id_)
        self._army_stats_list = []
        self._players_with_unsent_army_stats = []
        self._game_stats_service = game_stats_service
        self.game_service = game_service
        self._player_options: Dict[int, Dict[str, Any]] = defaultdict(dict)
        self.launched_at = None
        self.ended = False
        self._logger = logging.getLogger(
            "{}.{}".format(self.__class__.__qualname__, id_)
        )
        self.id = id_
        self.visibility = VisibilityState.PUBLIC
        self.max_players = 12
        self.host = host
        self.name = self.sanitize_name(name)
        self.map_id = None
        self.map_file_path = f'maps/{map_}.zip'
        self.map_scenario_path = None
        self.password = None
        self._players = []
        self.AIs = {}
        self.desyncs = 0
        self.validity = ValidityState.VALID
        self.game_mode = game_mode
        self._rating_type = rating_type
        self.state = GameState.INITIALIZING
        self._connections = {}
        self.enforce_rating = False
        self.gameOptions = {
            'FogOfWar': 'explored',
            'GameSpeed': 'normal',
            'Victory': Victory.DEMORALIZATION,
            'CheatsEnabled': 'false',
            'PrebuiltUnits': 'Off',
            'NoRushOption': 'Off',
            'TeamLock': 'locked',
            'AIReplacement': 'Off',
            'RestrictedCategories': 0
        }
        self.mods = {}
        self._is_hosted = asyncio.Future()

        self._logger.debug("%s created", self)
        asyncio.get_event_loop().create_task(self.timeout_game())

    async def timeout_game(self):
        # coop takes longer to set up
        tm = 30 if self.game_mode != 'coop' else 60
        await asyncio.sleep(tm)
        if self.state is GameState.INITIALIZING:
            self._is_hosted.set_exception(TimeoutError("Game setup timed out"))
            self._logger.debug("Game setup timed out.. Cancelling game")
            await self.on_game_end()

    @property
    def armies(self):
        return frozenset(
            self.get_player_option(player.id, 'Army')
            for player in self.players
        )

    @property
    def is_mutually_agreed_draw(self) -> bool:
        return self._results.is_mutually_agreed_draw(self.armies)

    @property
    def players(self):
        """
        Players in the game

        Depending on the state, it is either:
          - (LOBBY) The currently connected players
          - (LIVE) Players who participated in the game
          - Empty list
        :return: frozenset
        """
        if self.state is GameState.LOBBY:
            return frozenset(
                player for player in self._connections.keys()
                if player.id in self._player_options
            )
        else:
            return frozenset(
                player
                for player in self._players
                if self.get_player_option(player.id, 'Army') is not None
                and self.get_player_option(player.id, 'Army') >= 0
            )

    @property
    def connections(self):
        return self._connections.values()

    @property
    def teams(self):
        """
        A set of all teams of this game's players.
        """
        return frozenset(
            self.get_player_option(player.id, 'Team')
            for player in self.players
        )

    @property
    def is_ffa(self) -> bool:
        if len(self.players) < 3:
            return False

        return FFA_TEAM in self.teams

    @property
    def is_multi_team(self) -> bool:
        return len(self.teams) > 2

    @property
    def has_ai(self) -> bool:
        return len(self.AIs) > 0

    @property
    def is_even(self) -> bool:
        """
        Returns True iff all teams have the same player count, taking into account that players on the FFA team are in individual teams.
        Special cases:
         - Returns True if there are zero teams.
         - Returns False if there is a single team.
        """
        teams = self.get_team_sets()
        if len(teams) == 0:
            return True
        if len(teams) == 1:
            return False

        team_sizes = set(len(team) for team in teams)
        return len(team_sizes) == 1

    def get_team_sets(self) -> List[Set[Player]]:
        """
        Returns a list of teams represented as sets of players.
        Note that FFA players will be separated into individual teams.
        """
        if None in self.teams:
            raise GameError(
                "Missing team for at least one player. (player, team): {}"
                .format([(player, self.get_player_option(player.id, 'Team'))
                        for player in self.players])
            )

        teams = defaultdict(set)
        ffa_players = []
        for player in self.players:
            team_id = self.get_player_option(player.id, 'Team')
            if team_id == FFA_TEAM:
                ffa_players.append({player})
            else:
                teams[team_id].add(player)

        return list(teams.values()) + ffa_players

    async def await_hosted(self):
        return await asyncio.wait_for(self._is_hosted, None)

    def set_hosted(self, value: bool = True):
        if not self._is_hosted.done():
            self._is_hosted.set_result(value)

    async def add_result(
        self, reporter: int, army: int, result_type: str, score: int
    ):
        """
        As computed by the game.
        :param reporter: player ID
        :param army: the army number being reported for
        :param result_type: a string representing the result
        :param score: an arbitrary number assigned with the result
        :return:
        """
        if army not in self.armies:
            self._logger.debug(
                "Ignoring results for unknown army %s: %s %s reported by: %s",
                army, result_type, score, reporter
            )
            return

        try:
            outcome = GameOutcome(result_type.upper())
        except ValueError:
            outcome = GameOutcome.UNKNOWN

        result = GameResultReport(reporter, army, outcome, score)
        self._results.add(result)
        self._logger.info(
            "%s reported result for army %s: %s %s", reporter, army,
            result_type, score
        )

        self._process_pending_army_stats()

    def _process_pending_army_stats(self):
        for player in self._players_with_unsent_army_stats:
            army = self.get_player_option(player.id, 'Army')
            if army not in self._results:
                continue

            for result in self._results[army]:
                if result.outcome is not GameOutcome.UNKNOWN:
                    self._process_army_stats_for_player(player)
                    break

    def _process_army_stats_for_player(self, player):
        try:
            if (
                len(self._army_stats_list) == 0
                or self.gameOptions["CheatsEnabled"] != "false"
            ):
                return

            self._players_with_unsent_army_stats.remove(player)
            # Stat processing contacts the API and can take quite a while so
            # we don't want to await it
            asyncio.create_task(
                self._game_stats_service.process_game_stats(
                    player, self, self._army_stats_list
                )
            )
        except Exception:
            # Never let an error in processing army stats cascade
            self._logger.exception(
                "Army stats could not be processed from player %s in game %s",
                player, self
            )

    def add_game_connection(self, game_connection):
        """
        Add a game connection to this game
        :param game_connection:
        :return:
        """
        if game_connection.state != GameConnectionState.CONNECTED_TO_HOST:
            raise GameError(
                f"Invalid GameConnectionState: {game_connection.state}"
            )
        if self.state is not GameState.LOBBY and self.state is not GameState.LIVE:
            raise GameError(f"Invalid GameState: {self.state}")

        self._logger.info("Added game connection %s", game_connection)
        self._connections[game_connection.player] = game_connection

    async def remove_game_connection(self, game_connection):
        """
        Remove a game connection from this game

        Will trigger on_game_end if there are no more active connections to the game
        :param peer:
        :param
        :return: None
        """
        if game_connection not in self._connections.values():
            return

        player = game_connection.player
        del self._connections[player]
        del player.game

        if self.state is GameState.LOBBY and player.id in self._player_options:
            del self._player_options[player.id]

        await self.check_sim_end()

        self._logger.info("Removed game connection %s", game_connection)

        host_left_lobby = (
            player == self.host and self.state is not GameState.LIVE
        )

        if self.state is not GameState.ENDED and (
            self.ended or
            len(self._connections) == 0 or
            host_left_lobby
        ):
            await self.on_game_end()
        else:
            self._process_pending_army_stats()

    async def check_sim_end(self):
        if self.ended:
            return
        if self.state is not GameState.LIVE:
            return
        if [conn for conn in self.connections if not conn.finished_sim]:
            return
        self.ended = True
        async with self._db.acquire() as conn:
            await conn.execute(
                game_stats.update().where(
                    game_stats.c.id == self.id
                ).values(
                    endTime=sql_now()
                )
            )

    async def on_game_end(self):
        try:
            if self.state is GameState.LOBBY:
                self._logger.info("Game cancelled pre launch")
            elif self.state is GameState.INITIALIZING:
                self._logger.info("Game cancelled pre initialization")
            elif self.state is GameState.LIVE:
                self._logger.info("Game finished normally")

                if self.desyncs > 20:
                    await self.mark_invalid(ValidityState.TOO_MANY_DESYNCS)
                    return

                if time.time() - self.launched_at > 4 * 60 and self.is_mutually_agreed_draw:
                    self._logger.info("Game is a mutual draw")
                    await self.mark_invalid(ValidityState.MUTUAL_DRAW)
                    return

                if not self._results:
                    await self.mark_invalid(ValidityState.UNKNOWN_RESULT)
                    return

                await self.persist_results()

                game_results = await self.resolve_game_results()
                await self.game_service.publish_game_results(game_results)

                self._process_pending_army_stats()
        except Exception:    # pragma: no cover
            self._logger.exception("Error during game end")
        finally:
            self.set_hosted(value=False)

            self.state = GameState.ENDED

            self.game_service.mark_dirty(self)

    async def _run_pre_rate_validity_checks(self):
        pass

    async def resolve_game_results(self) -> EndedGameInfo:
        if self.state not in (GameState.LIVE, GameState.ENDED):
            raise GameError("Cannot rate game that has not been launched.")

        await self._run_pre_rate_validity_checks()

        basic_info = self.get_basic_info()
        team_outcomes = [GameOutcome.UNKNOWN for _ in basic_info.teams]

        if self.validity is ValidityState.VALID:
            try:
                team_player_partial_outcomes = [
                    {self.get_player_outcome(player) for player in team}
                    for team in basic_info.teams
                ]
                team_outcomes = resolve_game(team_player_partial_outcomes)
            except GameResolutionError:
                await self.mark_invalid(ValidityState.UNKNOWN_RESULT)

        try:
            commander_kills = {
                army_stats["name"]: army_stats["units"]["cdr"]["kills"]
                for army_stats in self._army_stats_list
            }
        except KeyError:
            commander_kills = {}

        return EndedGameInfo.from_basic(
            basic_info, self.validity, team_outcomes, commander_kills
        )


    async def load_results(self):
        """
        Load results from the database
        :return:
        """
        self._results = await GameResultReports.from_db(self._db, self.id)

    async def persist_results(self):
        """
        Persist game results into the database

        Requires the game to have been launched and the appropriate rows to exist in the database.
        :return:
        """

        self._logger.debug("Saving scores from game %s", self.id)
        scores = {}
        for player in self.players:
            army = self.get_player_option(player.id, 'Army')
            outcome = self.get_player_outcome(player)
            score = self.get_army_score(army)
            scores[player] = (score, outcome)
            self._logger.info(
                'Result for army %s, player: %s: score %s, outcome %s',
                army, player, score, outcome
            )

        async with self._db.acquire() as conn:
            rows = []
            for player, (score, outcome) in scores.items():
                self._logger.info(
                    "Score for player %s: score %s, outcome %s",
                    player, score, outcome,
                )
                rows.append(
                    {
                        "score": score,
                        "result": outcome.name.upper(),
                        "game_id": self.id,
                        "player_id": player.id,
                    }
                )

            update_statement = game_player_stats.update().where(
                    and_(
                        game_player_stats.c.gameId == bindparam("game_id"),
                        game_player_stats.c.playerId == bindparam("player_id"),
                    )
                ).values(
                    score=bindparam("score"),
                    scoreTime=sql_now(),
                    result=bindparam("result"),
                )
            await conn.execute(update_statement, rows)

    def get_basic_info(self) -> BasicGameInfo:
        return BasicGameInfo(
            self.id,
            self._rating_type,
            self.map_id,
            self.game_mode,
            list(self.mods.keys()),
            self.get_team_sets(),
        )

    def set_player_option(self, player_id: int, key: str, value: Any):
        """
        Set game-associative options for given player, by id

        :param player_id: The given player's id
        :param key: option key string
        :param value: option value
        """
        self._player_options[player_id][key] = value

    def get_player_option(self, player_id: int, key: str) -> Optional[Any]:
        """
        Retrieve game-associative options for given player, by their uid
        :param player_id: The id of the player
        :param key: The name of the option
        """
        return self._player_options[player_id].get(key)

    def set_ai_option(self, name, key, value):
        """
        This is a noop for now
        :param name: Name of the AI
        :param key: option key string
        :param value: option value
        :return:
        """
        if name not in self.AIs:
            self.AIs[name] = {}
        self.AIs[name][key] = value

    def clear_slot(self, slot_index):
        """
        A somewhat awkward message while we're still half-slot-associated with a bunch of data.

        Just makes sure that any players associated with this
        slot aren't assigned an army or team, and deletes any AI's.
        :param slot_index:
        :return:
        """
        for player in self.players:
            if self.get_player_option(player.id, 'StartSpot') == slot_index:
                self.set_player_option(player.id, 'Team', -1)
                self.set_player_option(player.id, 'Army', -1)
                self.set_player_option(player.id, 'StartSpot', -1)

        to_remove = []
        for ai in self.AIs:
            if self.AIs[ai]['StartSpot'] == slot_index:
                to_remove.append(ai)
        for item in to_remove:
            del self.AIs[item]

    async def validate_game_settings(self):
        """
        Mark the game invalid if it has non-compliant options
        """

        # Only allow ranked mods
        for mod_id in self.mods.keys():
            if mod_id not in self.game_service.ranked_mods:
                await self.mark_invalid(ValidityState.BAD_MOD)
                return

        if self.has_ai:
            await self.mark_invalid(ValidityState.HAS_AI_PLAYERS)
            return
        if self.is_multi_team:
            await self.mark_invalid(ValidityState.MULTI_TEAM)
            return
        if self.is_ffa:
            await self.mark_invalid(ValidityState.FFA_NOT_RANKED)
            return
        valid_options = {
            "AIReplacement": ("Off", ValidityState.HAS_AI_PLAYERS),
            "FogOfWar": ("explored", ValidityState.NO_FOG_OF_WAR),
            "CheatsEnabled": ("false", ValidityState.CHEATS_ENABLED),
            "PrebuiltUnits": ("Off", ValidityState.PREBUILT_ENABLED),
            "NoRushOption": ("Off", ValidityState.NORUSH_ENABLED),
            "RestrictedCategories": (0, ValidityState.BAD_UNIT_RESTRICTIONS),
            "TeamLock": ("locked", ValidityState.UNLOCKED_TEAMS)
        }
        if await self._validate_game_options(valid_options) is False:
            return

        if self.game_mode in ('faf', 'ladder1v1'):
            await self._validate_faf_game_settings()
        elif self.game_mode == 'coop':
            await self._validate_coop_game_settings()

    async def _validate_game_options(
        self, valid_options: Dict[str, Tuple[Any, ValidityState]]
    ) -> bool:
        for key, value in self.gameOptions.items():
            if key in valid_options:
                (valid_value, validity_state) = valid_options[key]
                if self.gameOptions[key] != valid_value:
                    await self.mark_invalid(validity_state)
                    return False
        return True

    async def _validate_coop_game_settings(self):
        """
        Checks which only apply to the coop mode
        """

        valid_options = {
            "Victory": (Victory.SANDBOX, ValidityState.WRONG_VICTORY_CONDITION),
            "TeamSpawn": ("fixed", ValidityState.SPAWN_NOT_FIXED),
            "RevealedCivilians": ("No", ValidityState.CIVILIANS_REVEALED),
            "Difficulty": (3, ValidityState.WRONG_DIFFICULTY),
            "Expansion": (1, ValidityState.EXPANSION_DISABLED),
        }
        await self._validate_game_options(valid_options)

    async def _validate_faf_game_settings(self):
        """
        Checks which only apply to the faf or ladder1v1 mode
        """
        if None in self.teams or not self.is_even:
            await self.mark_invalid(ValidityState.UNEVEN_TEAMS_NOT_RANKED)
            return

        if len(self.players) < 2:
            await self.mark_invalid(ValidityState.SINGLE_PLAYER)
            return

        valid_options = {
            "Victory": (Victory.DEMORALIZATION, ValidityState.WRONG_VICTORY_CONDITION)
        }
        await self._validate_game_options(valid_options)

    async def launch(self):
        """
        Mark the game as live.

        Freezes the set of active players so they are remembered if they drop.
        :return: None
        """
        assert self.state is GameState.LOBBY
        self.launched_at = time.time()
        self._players = self.players
        self._players_with_unsent_army_stats = list(self._players)

        self.state = GameState.LIVE
        self._logger.info("Game launched")

        await self.on_game_launched()
        await self.validate_game_settings()

    async def on_game_launched(self):
        for player in self.players:
            player.state = PlayerState.PLAYING
        await self.update_game_stats()
        await self.update_game_player_stats()

    async def update_game_stats(self):
        """
        Runs at game-start to populate the game_stats table (games that start are ones we actually
        care about recording stats for, after all).
        """
        assert self.host is not None

        async with self._db.acquire() as conn:
            # Determine if the map is blacklisted, and invalidate the game for ranking purposes if
            # so, and grab the map id at the same time.
            result = await conn.execute(
                "SELECT id, ranked FROM map_version "
                "WHERE lower(filename) = lower(%s)", (self.map_file_path, )
            )
            row = await result.fetchone()

            if row:
                self.map_id = row['id']

            if (not row or not row['ranked']) and self.validity is ValidityState.VALID:
                await self.mark_invalid(ValidityState.BAD_MAP)

            modId = self.game_service.featured_mods[self.game_mode].id

            # Write out the game_stats record.
            # In some cases, games can be invalidated while running: we check for those cases when
            # the game ends and update this record as appropriate.

            game_type = str(self.gameOptions.get("Victory").value)
            await conn.execute(
                game_stats.insert().values(
                    id=self.id,
                    gameType=game_type,
                    gameMod=modId,
                    host=self.host.id,
                    mapId=self.map_id,
                    gameName=self.name,
                    validity=self.validity.value,
                )
            )

    async def update_game_player_stats(self):
        query_args = []
        for player in self.players:
            options = {
                key: self.get_player_option(player.id, key)
                for key in ["Team", "StartSpot", "Color", "Faction"]
            }

            is_observer = (
                options["Team"] is None
                or options["Team"] < 0
                or options["StartSpot"] is None
                or options["StartSpot"] < 0
            )
            if is_observer:
                continue

            if self.game_mode == 'ladder1v1':
                mean, deviation = player.ratings[RatingType.LADDER_1V1]
            else:
                mean, deviation = player.ratings[RatingType.GLOBAL]

            query_args.append(
                {
                    "gameId": self.id,
                    "playerId": player.id,
                    "faction": options["Faction"],
                    "color": options["Color"],
                    "team": options["Team"],
                    "place": options["StartSpot"],
                    "mean": mean,
                    "deviation": deviation,
                    "AI": 0,
                    "score": 0,
                }
            )
        if not query_args:
            self._logger.warning("No player options available!")
            return

        try:
            async with self._db.acquire() as conn:
                await conn.execute(game_player_stats.insert().values(query_args))
        except pymysql.MySQLError:
            self._logger.exception(
                "Failed to update game_player_stats. Query args %s:", query_args
            )
            raise

    def sanitize_name(self, name: str) -> str:
        """
        Replaces sequences of non-latin characters with an underscore and truncates the string to 128 characters
        Avoids the game name to crash the mysql INSERT query by being longer than the column's max size or by
        containing non-latin1 characters
        """
        return re.sub('[^\x20-\xFF]+', '_', name)[:128]

    async def mark_invalid(self, new_validity_state: ValidityState):
        self._logger.info(
            "Marked as invalid because: %s", repr(new_validity_state)
        )
        self.validity = new_validity_state

        # If we haven't started yet, the invalidity will be persisted to the database when we start.
        # Otherwise, we have to do a special update query to write this information out.
        if self.state is not GameState.LIVE:
            return

        # Currently, we can only end up here if a game desynced or was a custom game that terminated
        # too quickly.
        async with self._db.acquire() as conn:
            await conn.execute(
                game_stats.update().where(
                    game_stats.c.id == self.id
                ).values(
                    validity=new_validity_state.value
                )
            )

    def get_army_score(self, army):
        return self._results.score(army)

    def get_player_outcome(self, player):
        army = self.get_player_option(player.id, 'Army')
        if army is None:
            return GameOutcome.UNKNOWN

        return self._results.outcome(army)

    def report_army_stats(self, stats_json):
        self._army_stats_list = json.loads(stats_json)["stats"]
        self._process_pending_army_stats()

    def to_dict(self):
        client_state = {
            GameState.LOBBY: 'open',
            GameState.LIVE: 'playing',
            GameState.ENDED: 'closed',
            GameState.INITIALIZING: 'closed',
        }.get(self.state, 'closed')
        return {
            "command": "game_info",
            "visibility": VisibilityState.to_string(self.visibility),
            "password_protected": self.password is not None,
            "uid": self.id,
            "title": self.name,
            "state": client_state,
            "featured_mod": self.game_mode,
            "sim_mods": self.mods,
            "mapname": self.map_folder_name,
            "map_file_path": self.map_file_path,
            "host": self.host.login if self.host else '',
            "num_players": len(self.players),
            "max_players": self.max_players,
            "launched_at": self.launched_at,
            "teams": {
                team: [
                    player.login for player in self.players
                    if self.get_player_option(player.id, 'Team') == team
                ]
                for team in self.teams
            }
        }

    @property
    def map_folder_name(self):
        """
        Map folder name
        :return:
        """
        try:
            return str(self.map_scenario_path.split('/')[2]).lower()
        except (IndexError, AttributeError):
            if self.map_file_path:
                return self.map_file_path[5:-4].lower()
            else:
                return 'scmp_009'

    def __eq__(self, other):
        if not isinstance(other, Game):
            return False
        else:
            return self.id == other.id

    def __hash__(self):
        return self.id.__hash__()

    def __str__(self):
        return "Game({},{},{},{})".format(
            self.id, self.host.login if self.host else '', self.map_file_path,
            len(self.players)
        )
