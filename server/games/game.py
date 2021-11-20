import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, Iterable, Optional

from sqlalchemy import and_, bindparam
from sqlalchemy.exc import DBAPIError
from sqlalchemy.sql.functions import now as sql_now

from server.config import FFA_TEAM
from server.db.models import (
    game_player_stats,
    game_stats,
    matchmaker_queue_game
)
from server.games.game_results import (
    ArmyOutcome,
    ArmyReportedOutcome,
    ArmyResult,
    GameOutcome,
    GameResolutionError,
    GameResultReport,
    GameResultReports,
    resolve_game
)
from server.rating import InclusiveRange, RatingType

from ..players import Player, PlayerState
from .typedefs import (
    FA,
    BasicGameInfo,
    EndedGameInfo,
    FeaturedModType,
    GameConnectionState,
    GameState,
    GameType,
    ValidityState,
    Victory,
    VisibilityState
)


class GameError(Exception):
    pass


class Game():
    """
    Object that lasts for the lifetime of a game on FAF.
    """
    game_type = GameType.CUSTOM

    def __init__(
        self,
        id_: int,
        database: "FAFDatabase",
        game_service: "GameService",
        game_stats_service: "GameStatsService",
        host: Optional[Player] = None,
        name: str = "None",
        map_: str = "SCMP_007",
        game_mode: str = FeaturedModType.FAF,
        matchmaker_queue_id: Optional[int] = None,
        rating_type: Optional[str] = None,
        displayed_rating_range: Optional[InclusiveRange] = None,
        enforce_rating_range: bool = False,
        max_players: int = 12,
        setup_timeout: int = 60,
    ):
        self._db = database
        self._results = GameResultReports(id_)
        self._army_stats_list = []
        self._players_with_unsent_army_stats = []
        self._game_stats_service = game_stats_service
        self.game_service = game_service
        self._player_options: dict[int, dict[str, Any]] = defaultdict(dict)
        self.launched_at = None
        self.ended = False
        self._logger = logging.getLogger(
            f"{self.__class__.__qualname__}.{id_}"
        )
        self.id = id_
        self.visibility = VisibilityState.PUBLIC
        self.max_players = max_players
        self.host = host
        self.name = name
        self.map_id = None
        self.map_file_path = f"maps/{map_}.zip"
        self.map_scenario_path = None
        self.password = None
        self._players_at_launch: list[Player] = []
        self.AIs = {}
        self.desyncs = 0
        self.validity = ValidityState.VALID
        self.game_mode = game_mode
        self.rating_type = rating_type or RatingType.GLOBAL
        self.displayed_rating_range = displayed_rating_range or InclusiveRange()
        self.enforce_rating_range = enforce_rating_range
        self.matchmaker_queue_id = matchmaker_queue_id
        self.state = GameState.INITIALIZING
        self._connections = {}
        self.enforce_rating = False
        self.gameOptions = {
            "FogOfWar": "explored",
            "GameSpeed": "normal",
            "Victory": Victory.DEMORALIZATION,
            "CheatsEnabled": "false",
            "PrebuiltUnits": "Off",
            "NoRushOption": "Off",
            "TeamLock": "locked",
            "AIReplacement": "Off",
            "RestrictedCategories": 0,
            "Unranked": "No"
        }
        self.mods = {}
        self._hosted_event = asyncio.Event()
        self._launched_event = asyncio.Event()

        self._logger.debug("%s created", self)
        asyncio.get_event_loop().create_task(self.timeout_game(setup_timeout))

    async def timeout_game(self, timeout: int = 60):
        await asyncio.sleep(timeout)
        if self.state is GameState.INITIALIZING:
            self._logger.debug("Game setup timed out, cancelling game")
            await self.on_game_end()

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value: str):
        """
        Verifies that names only contain ascii characters.
        """
        if not value.isascii():
            raise ValueError("Name must be ascii!")

        self.set_name_unchecked(value)

    def set_name_unchecked(self, value: str):
        """
        Sets the game name without doing any validity checks.

        Truncates the game name to avoid crashing mysql INSERT statements.
        """
        max_len = game_stats.c.gameName.type.length
        self._name = value[:max_len]

    @property
    def armies(self) -> frozenset[int]:
        return frozenset(
            self.get_player_option(player.id, "Army")
            for player in self.players
        )

    @property
    def is_mutually_agreed_draw(self) -> bool:
        return self._results.is_mutually_agreed_draw(self.armies)

    @property
    def players(self) -> list[Player]:
        """
        Players in the game

        Depending on the state, it is either:
          - (LOBBY) The currently connected players
          - (LIVE) Players who participated in the game
          - Empty list
        """
        if self.state is GameState.LOBBY:
            return self.get_connected_players()
        else:
            return self._players_at_launch

    def get_connected_players(self) -> list[Player]:
        """
        Get a collection of all players currently connected to the game.
        """
        return [
            player for player in self._connections.keys()
            if player.id in self._player_options
        ]

    def _is_observer(self, player: Player) -> bool:
        army = self.get_player_option(player.id, "Army")
        return army is None or army < 0

    @property
    def connections(self) -> Iterable["GameConnection"]:
        return self._connections.values()

    @property
    def teams(self) -> frozenset[int]:
        """
        A set of all teams of this game's players.
        """
        return frozenset(
            self.get_player_option(player.id, "Team")
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
        If teams are balanced taking into account that players on the FFA team
        are on individual teams.

        # Returns
        `True` iff all teams have the same player count.

        Special cases:

        - `True` if there are zero teams.
        - `False` if there is a single team.
        """
        teams = self.get_team_sets()
        if len(teams) == 0:
            return True
        if len(teams) == 1:
            return False

        team_sizes = set(len(team) for team in teams)
        return len(team_sizes) == 1

    def get_team_sets(self) -> list[set[Player]]:
        """
        Returns a list of teams represented as sets of players.
        Note that FFA players will be separated into individual teams.
        """
        if None in self.teams:
            raise GameError(
                "Missing team for at least one player. (player, team): {}"
                .format([(player, self.get_player_option(player.id, "Team"))
                        for player in self.players])
            )

        teams = defaultdict(set)
        ffa_players = []
        for player in self.players:
            team_id = self.get_player_option(player.id, "Team")
            if team_id == FFA_TEAM:
                ffa_players.append({player})
            else:
                teams[team_id].add(player)

        return list(teams.values()) + ffa_players

    async def wait_hosted(self, timeout: float):
        return await asyncio.wait_for(
            self._hosted_event.wait(),
            timeout=timeout
        )

    def set_hosted(self):
        self._hosted_event.set()

    async def wait_launched(self, timeout: float):
        return await asyncio.wait_for(
            self._launched_event.wait(),
            timeout=timeout
        )

    async def add_result(
        self,
        reporter: int,
        army: int,
        result_type: str,
        score: int,
        result_metadata: frozenset[str] = frozenset(),
    ):
        """
        As computed by the game.

        # Params
        - `reporter`: player ID
        - `army`: the army number being reported for
        - `result_type`: a string representing the result
        - `score`: an arbitrary number assigned with the result
        - `result_metadata`: everything preceding the `result_type` in the
            result message from the game, one or more words, optional
        """
        if army not in self.armies:
            self._logger.debug(
                "Ignoring results for unknown army %s: %s %s reported by: %s",
                army, result_type, score, reporter
            )
            return

        try:
            outcome = ArmyReportedOutcome(result_type.upper())
        except ValueError:
            self._logger.debug(
                "Ignoring result reported by %s for army %s: %s %s",
                reporter, army, result_type, score
            )
            return

        result = GameResultReport(reporter, army, outcome, score, result_metadata)
        self._results.add(result)
        self._logger.info(
            "%s reported result for army %s: %s %s", reporter, army,
            result_type, score
        )

        self._process_pending_army_stats()

    def _process_pending_army_stats(self):
        for player in self._players_with_unsent_army_stats:
            army = self.get_player_option(player.id, "Army")
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
        Add a game connection to this game.
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
        Remove a game connection from this game.

        Will trigger `on_game_end` if there are no more active connections to the
        game.
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

                await self.process_game_results()

                self._process_pending_army_stats()
        except Exception:    # pragma: no cover
            self._logger.exception("Error during game end")
        finally:
            self.state = GameState.ENDED

            self.game_service.mark_dirty(self)

    async def _run_pre_rate_validity_checks(self):
        pass

    async def process_game_results(self):
        if not self._results:
            await self.mark_invalid(ValidityState.UNKNOWN_RESULT)
            return

        await self.persist_results()

        game_results = await self.resolve_game_results()
        await self.game_service.publish_game_results(game_results)

    async def resolve_game_results(self) -> EndedGameInfo:
        if self.state not in (GameState.LIVE, GameState.ENDED):
            raise GameError("Cannot rate game that has not been launched.")

        await self._run_pre_rate_validity_checks()

        basic_info = self.get_basic_info()

        team_army_results = [
            [self.get_army_results(player) for player in team]
            for team in basic_info.teams
        ]

        team_outcomes = [GameOutcome.UNKNOWN for _ in basic_info.teams]

        if self.validity is ValidityState.VALID:
            team_player_partial_outcomes = [
                {self.get_player_outcome(player) for player in team}
                for team in basic_info.teams
            ]

            try:
                # TODO: Remove override once game result messages are reliable
                team_outcomes = (
                    self._outcome_override_hook()
                    or resolve_game(team_player_partial_outcomes)
                )
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
            basic_info,
            self.validity,
            team_outcomes,
            commander_kills,
            team_army_results,
        )

    def _outcome_override_hook(self) -> Optional[list[GameOutcome]]:
        return None

    async def load_results(self):
        """
        Load results from the database
        """
        self._results = await GameResultReports.from_db(self._db, self.id)

    async def persist_results(self):
        """
        Persist game results into the database

        Requires the game to have been launched and the appropriate rows to
        exist in the database.
        """

        self._logger.debug("Saving scores from game %s", self.id)
        scores = {}
        for player in self.players:
            army = self.get_player_option(player.id, "Army")
            outcome = self.get_player_outcome(player)
            score = self.get_army_score(army)
            scores[player] = (score, outcome)
            self._logger.info(
                "Result for army %s, player: %s: score %s, outcome %s",
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
            await conn.deadlock_retry_execute(update_statement, rows)

    def get_basic_info(self) -> BasicGameInfo:
        return BasicGameInfo(
            self.id,
            self.rating_type,
            self.map_id,
            self.game_mode,
            list(self.mods.keys()),
            self.get_team_sets(),
        )

    def set_player_option(self, player_id: int, key: str, value: Any):
        """
        Set game-associative options for given player, by id
        """
        self._player_options[player_id][key] = value

    def get_player_option(self, player_id: int, key: str) -> Optional[Any]:
        """
        Retrieve game-associative options for given player, by their uid
        """
        return self._player_options[player_id].get(key)

    def set_ai_option(self, name, key, value):
        """
        Set game-associative options for given AI, by name
        """
        if name not in self.AIs:
            self.AIs[name] = {}
        self.AIs[name][key] = value

    def clear_slot(self, slot_index):
        """
        A somewhat awkward message while we're still half-slot-associated with
        a bunch of data.

        Just makes sure that any players associated with this slot aren't
        assigned an army or team, and deletes any AI's.
        """
        for player in self.players:
            if self.get_player_option(player.id, "StartSpot") == slot_index:
                self.set_player_option(player.id, "Team", -1)
                self.set_player_option(player.id, "Army", -1)
                self.set_player_option(player.id, "StartSpot", -1)

        to_remove = []
        for ai in self.AIs:
            if self.AIs[ai]["StartSpot"] == slot_index:
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
            "AIReplacement": (FA.DISABLED, ValidityState.HAS_AI_PLAYERS),
            "FogOfWar": ("explored", ValidityState.NO_FOG_OF_WAR),
            "CheatsEnabled": (FA.DISABLED, ValidityState.CHEATS_ENABLED),
            "PrebuiltUnits": (FA.DISABLED, ValidityState.PREBUILT_ENABLED),
            "NoRushOption": (FA.DISABLED, ValidityState.NORUSH_ENABLED),
            "RestrictedCategories": (0, ValidityState.BAD_UNIT_RESTRICTIONS),
            "TeamLock": ("locked", ValidityState.UNLOCKED_TEAMS),
            "Unranked": (FA.DISABLED, ValidityState.HOST_SET_UNRANKED)
        }
        if await self._validate_game_options(valid_options) is False:
            return

        await self.validate_game_mode_settings()

    async def validate_game_mode_settings(self):
        """
        A subset of checks that need to be overridden in coop games.
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

    async def _validate_game_options(
        self, valid_options: dict[str, tuple[Any, ValidityState]]
    ) -> bool:
        for key, value in self.gameOptions.items():
            if key in valid_options:
                (valid_value, validity_state) = valid_options[key]
                if valid_value != self.gameOptions[key]:
                    await self.mark_invalid(validity_state)
                    return False
        return True

    async def launch(self):
        """
        Mark the game as live.

        Freezes the set of active players so they are remembered if they drop.
        """
        assert self.state is GameState.LOBBY
        self.launched_at = time.time()
        # Freeze currently connected players since we need them for rating when
        # the game ends.
        self._players_at_launch = [
            player for player in self.get_connected_players()
            if not self._is_observer(player)
        ]
        self._players_with_unsent_army_stats = list(self._players_at_launch)

        self.state = GameState.LIVE

        await self.on_game_launched()
        await self.validate_game_settings()

        self._launched_event.set()
        self._logger.info("Game launched")

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
                "WHERE lower(filename) = lower(:filename)",
                filename=self.map_file_path
            )
            row = result.fetchone()

        is_generated = (self.map_file_path and "neroxis_map_generator" in self.map_file_path)

        if row:
            self.map_id = row.id

        if (
            self.validity is ValidityState.VALID
            and ((row and not row.ranked) or (not row and not is_generated))
        ):
            await self.mark_invalid(ValidityState.BAD_MAP)

        modId = self.game_service.featured_mods[self.game_mode].id

        # Write out the game_stats record.
        # In some cases, games can be invalidated while running: we check for those cases when
        # the game ends and update this record as appropriate.

        game_type = str(self.gameOptions.get("Victory").value)

        async with self._db.acquire() as conn:
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

            if self.matchmaker_queue_id is not None:
                await conn.execute(
                    matchmaker_queue_game.insert().values(
                        matchmaker_queue_id=self.matchmaker_queue_id,
                        game_stats_id=self.id,
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

            # DEPRECATED: Rating changes are persisted by the rating service
            # in the `leaderboard_rating_journal` table.
            mean, deviation = player.ratings[self.rating_type]

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
        except DBAPIError:
            self._logger.exception(
                "Failed to update game_player_stats. Query args %s:", query_args
            )
            raise

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

    def get_player_outcome(self, player: Player) -> ArmyOutcome:
        army = self.get_player_option(player.id, "Army")
        if army is None:
            return ArmyOutcome.UNKNOWN

        return self._results.outcome(army)

    def get_army_results(self, player: Player) -> ArmyResult:
        army = self.get_player_option(player.id, "Army")
        return ArmyResult(
            player.id,
            army,
            self.get_player_outcome(player).name,
            self._results.metadata(army),
        )

    def report_army_stats(self, stats_json):
        self._army_stats_list = json.loads(stats_json)["stats"]
        self._process_pending_army_stats()

    def is_visible_to_player(self, player: Player) -> bool:
        """
        Determine if a player should see this game in their games list.

        Note: This is a *hot* function, it can have significant impacts on
        performance.
        """
        if self.host is None:
            return False

        if player == self.host or player in self._connections:
            return True

        if (
            self.enforce_rating_range
            and player.ratings[self.rating_type].displayed()
            not in self.displayed_rating_range
        ):
            return False

        if self.visibility is VisibilityState.FRIENDS:
            return player.id in self.host.friends
        else:
            return player.id not in self.host.foes

    def to_dict(self):
        client_state = {
            GameState.LOBBY: "open",
            GameState.LIVE: "playing",
            GameState.ENDED: "closed",
            GameState.INITIALIZING: "closed",
        }.get(self.state, "closed")
        connected_players = self.get_connected_players()
        return {
            "command": "game_info",
            "visibility": self.visibility.value,
            "password_protected": self.password is not None,
            "uid": self.id,
            "title": self.name,
            "state": client_state,
            "game_type": self.game_type.value,
            "featured_mod": self.game_mode,
            "sim_mods": self.mods,
            "mapname": self.map_folder_name,
            "map_file_path": self.map_file_path,
            "host": self.host.login if self.host else "",
            "num_players": len(connected_players),
            "max_players": self.max_players,
            "launched_at": self.launched_at,
            "rating_type": self.rating_type,
            "rating_min": self.displayed_rating_range.lo,
            "rating_max": self.displayed_rating_range.hi,
            "enforce_rating_range": self.enforce_rating_range,
            "teams": {
                team: [
                    player.login for player in connected_players
                    if self.get_player_option(player.id, "Team") == team
                ]
                for team in self.teams if team is not None
            }
        }

    @property
    def map_folder_name(self) -> str:
        """
        Map folder name
        """
        try:
            return str(self.map_scenario_path.split("/")[2]).lower()
        except (IndexError, AttributeError):
            if self.map_file_path:
                return self.map_file_path[5:-4].lower()
            else:
                return "scmp_009"

    def __eq__(self, other):
        if not isinstance(other, Game):
            return False
        else:
            return self.id == other.id

    def __hash__(self):
        return self.id.__hash__()

    def __str__(self) -> str:
        return (
            f"Game({self.id}, {self.host.login if self.host else ''}, "
            f"{self.map_file_path})"
        )
