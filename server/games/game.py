import asyncio
import functools
import logging
import re
import time
from collections import Counter, defaultdict
from enum import Enum, unique
from typing import Any, Dict, Optional, Tuple, Union

import server.db as db
import trueskill
from trueskill import Rating

from ..abc.base_game import BaseGame, GameConnectionState, InitMode
from ..players import Player, PlayerState


@unique
class GameState(Enum):
    INITIALIZING = 0
    LOBBY = 1
    LIVE = 2
    ENDED = 3


@unique
class Victory(Enum):
    DEMORALIZATION = 0
    DOMINATION = 1
    ERADICATION = 2
    SANDBOX = 3

    @staticmethod
    def from_gpgnet_string(value: str) -> Optional["Victory"]:
        """
        :param value: The string to convert from

        :return: Victory or None if the string is not valid
        """
        return {
            "demoralization": Victory.DEMORALIZATION,
            "domination": Victory.DOMINATION,
            "eradication": Victory.ERADICATION,
            "sandbox": Victory.SANDBOX
        }.get(value)


@unique
class VisibilityState(Enum):
    PUBLIC = 0
    FRIENDS = 1

    @staticmethod
    def from_string(value: str) -> Optional["VisibilityState"]:
        """
        :param value: The string to convert from

        :return: VisibilityState or None if the string is not valid
        """
        return {
            "public": VisibilityState.PUBLIC,
            "friends": VisibilityState.FRIENDS
        }.get(value)

    def to_string(self) -> Optional[str]:
        return {
            VisibilityState.PUBLIC: "public",
            VisibilityState.FRIENDS: "friends"
        }.get(self)


# Identifiers must be kept in sync with the contents of the invalid_game_reasons table.
# New reasons added should have a description added to that table. Identifiers should never be
# reused, and values should never be deleted from invalid_game_reasons.
@unique
class ValidityState(Enum):
    VALID = 0
    TOO_MANY_DESYNCS = 1
    WRONG_VICTORY_CONDITION = 2
    NO_FOG_OF_WAR = 3
    CHEATS_ENABLED = 4
    PREBUILT_ENABLED = 5
    NORUSH_ENABLED = 6
    BAD_UNIT_RESTRICTIONS = 7
    BAD_MAP = 8
    TOO_SHORT = 9
    BAD_MOD = 10
    COOP_NOT_RANKED = 11
    MUTUAL_DRAW = 12
    SINGLE_PLAYER = 13
    FFA_NOT_RANKED = 14
    UNEVEN_TEAMS_NOT_RANKED = 15
    UNKNOWN_RESULT = 16
    UNLOCKED_TEAMS = 17
    MULTI_TEAM = 18
    HAS_AI_PLAYERS = 19
    CIVILIANS_REVEALED = 20
    WRONG_DIFFICULTY = 21
    EXPANSION_DISABLED = 22
    SPAWN_NOT_FIXED = 23
    OTHER_UNRANK = 24


@unique
class GameOutcome(Enum):
    VICTORY = 1
    DEFEAT = 2
    DRAW = 3
    MUTUAL_DRAW = 4

    @staticmethod
    def from_string(value: str) -> Optional["GameOutcome"]:
        """
        :param value: The string to convert from

        :return: VisibilityState or None if the string is not valid
        """
        return {
            "victory": GameOutcome.VICTORY,
            "defeat": GameOutcome.DEFEAT,
            "draw": GameOutcome.DRAW,
            "mutual_draw": GameOutcome.MUTUAL_DRAW
        }.get(value)


class GameError(Exception):
    pass


class Game(BaseGame):
    """
    Object that lasts for the lifetime of a game on FAF.
    """
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(
        self,
        id_: int,
        game_service: "GameService",
        game_stats_service: "GameStatsService",
        host: Optional[Player]=None,
        name: str='None',
        map_: str='SCMP_007',
        game_mode: str='faf'
    ):
        super().__init__()
        self._results = {}
        self._army_stats = None
        self._players_with_unsent_army_stats = []
        self._game_stats_service = game_stats_service
        self.game_service = game_service
        self._player_options: Dict[int, Dict[str, Any]] = defaultdict(dict)
        self.launched_at = None
        self.ended = False
        self._logger = logging.getLogger("{}.{}".format(self.__class__.__qualname__, id_))
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

    async def sleep(self, n):
        return await asyncio.sleep(n)

    async def timeout_game(self):
        # coop takes longer to set up
        tm = 30 if self.game_mode != 'coop' else 60
        await self.sleep(tm)
        if self.state == GameState.INITIALIZING:
            self._is_hosted.set_exception(TimeoutError("Game setup timed out"))
            self._logger.debug("Game setup timed out.. Cancelling game")
            await self.on_game_end()

    @property
    def armies(self):
        return frozenset({self.get_player_option(player.id, 'Army')
                          for player in self.players})

    @property
    def is_mutually_agreed_draw(self) -> bool:
        # Don't count non-reported games as mutual draws
        if not len(self._results):
            return False
        for army in self.armies:
            if army in self._results:
                for result in self._results[army]:
                    if result[1] != 'mutual_draw':
                        return False
            else:
                return False
        return True

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
        if self.state == GameState.LOBBY:
            return frozenset(self._connections.keys())
        else:
            return frozenset({player for player in self._players
                              if self.get_player_option(player.id, 'Army') is not None
                              and self.get_player_option(player.id, 'Army') >= 0})

    @property
    def connections(self):
        return self._connections.values()

    @property
    def teams(self):
        return frozenset({self.get_player_option(player.id, 'Team')
                          for player in self.players})

    @property
    def is_ffa(self) -> bool:
        if len(self.players) < 3:
            return False

        teams = set()
        for player in self.players:
            team = self.get_player_option(player.id, 'Team')
            if team != 1:
                if team in teams:
                    return False
                teams.add(team)

        return True

    @property
    def is_multi_team(self) -> bool:
        return len(self.teams) > 2

    @property
    def has_ai(self) -> bool:
        return len(self.AIs) > 0

    @property
    def is_even(self) -> bool:
        teams = self.team_count()
        if 1 in teams: # someone is in ffa team, all teams need to have 1 player
            c = 1
            teams.pop(1)
        else:
            n = len(teams)
            if n <= 1: # 0 teams are considered even, single team not
                return n == 0

            # all teams needs to have same count as the first
            c = list(teams.values())[0]

        for _, v in teams.items():
            if v != c:
                return False

        return True

    def team_count(self):
        """
        Returns a dictionary containing team ids and their respective number of
        players.
        Example:
            Team 1 has 2 players
            Team 2 has 3 players
            team 3 has 1 player
            Return value is:
            {
                1: 2,
                2: 3,
                3: 1
            }
        """
        teams = defaultdict(int)
        for player in self.players:
            teams[self.get_player_option(player.id, 'Team')] += 1

        return teams

    async def await_hosted(self):
        return await asyncio.wait_for(self._is_hosted, None)

    def set_hosted(self, value: bool=True):
        if not self._is_hosted.done():
            self._is_hosted.set_result(value)

    def outcome(self, player: Player) -> Optional[GameOutcome]:
        """
        Determines what the game outcome was for a given player. Did the
        player win, lose, draw?

        :param player: The player who's perspective we want
        :return: GameOutcome or None if the outcome could not be determined
        """
        army = self.get_player_option(player.id, 'Army')
        if army not in self._results:
            return None

        outcomes = set()
        for result in self._results[army]:
            outcomes.add(GameOutcome.from_string(result[1]))

        # If there was exactly 1 outcome then return it
        if len(outcomes) == 1:
            return outcomes.pop()

        # If there were no outcomes, or the outcomes do not agree then we can't
        # determine the outcome
        return None

    async def add_result(self, reporter: Union[Player, int], army: int, result_type: str, score: int):
        """
        As computed by the game.
        :param reporter: a player instance or the player ID
        :param army: the army number being reported for
        :param result_type: a string representing the result
        :param score: an arbitrary number assigned with the result
        :return:
        """
        if army not in self.armies:
            self._logger.debug(
                "Ignoring results for unknown army %s: %s %s reported by: %s", army, result_type, score, reporter)
            return

        if army not in self._results:
            self._results[army] = []
        self._logger.info("%s reported result for army %s: %s %s", reporter, army, result_type, score)
        self._results[army].append((reporter, result_type.lower(), score))

        await self._process_pending_army_stats()

    async def _process_pending_army_stats(self):
        for player in self._players_with_unsent_army_stats:
            army = self.get_player_option(player.id, 'Army')
            if army not in self._results:
                continue

            for result in self._results[army]:
                if result[1] in ['defeat', 'victory', 'draw', 'mutual_draw']:
                    await self._process_army_stats_for_player(player)
                    break

    async def _process_army_stats_for_player(self, player):
        try:
            if self._army_stats is None or self.gameOptions["CheatsEnabled"] != "false":
                return

            self._players_with_unsent_army_stats.remove(player)
            await self._game_stats_service.process_game_stats(player, self, self._army_stats)
        except Exception as e:
            # Never let an error in processing army stats cascade
            self._logger.exception("Army stats could not be processed from player %s in game %s", player, self)

    def add_game_connection(self, game_connection):
        """
        Add a game connection to this game
        :param game_connection:
        :return:
        """
        if game_connection.state != GameConnectionState.CONNECTED_TO_HOST:
            raise GameError("Invalid GameConnectionState: {}".format(game_connection.state))
        if self.state != GameState.LOBBY and self.state != GameState.LIVE:
            raise GameError("Invalid GameState: {state}".format(state=self.state))
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
        del self._connections[game_connection.player]
        if game_connection.player:
            del game_connection.player.game
        await self.check_sim_end()

        self._logger.info("Removed game connection %s", game_connection)

        def host_left_lobby() -> bool:
            return game_connection.player == self.host and self.state != GameState.LIVE

        if len(self._connections) == 0 or host_left_lobby():
            await self.on_game_end()
        else:
            await self._process_pending_army_stats()

    async def check_sim_end(self):
        if self.ended:
            return
        if self.state != GameState.LIVE:
            return
        if len([conn for conn in self._connections.values() if not conn.finished_sim]) > 0:
            return
        self.ended = True
        async with db.engine.acquire() as conn:
            await conn.execute(
                "UPDATE game_stats "
                "SET endTime = NOW() "
                "WHERE id = %s", (self.id,))

    async def on_game_end(self):
        try:
            if self.state == GameState.LOBBY:
                self._logger.info("Game cancelled pre launch")
            elif self.state == GameState.INITIALIZING:
                self._logger.info("Game cancelled pre initialization")
            elif self.state == GameState.LIVE:
                self._logger.info("Game finished normally")

                if self.desyncs > 20:
                    await self.mark_invalid(ValidityState.TOO_MANY_DESYNCS)
                    return

                if time.time() - self.launched_at > 4*60 and self.is_mutually_agreed_draw:
                    self._logger.info("Game is a mutual draw")
                    await self.mark_invalid(ValidityState.MUTUAL_DRAW)
                    return

                if len(self._results) == 0:
                    await self.mark_invalid(ValidityState.UNKNOWN_RESULT)
                    return

                await self.persist_results()
                await self.rate_game()
                await self._process_pending_army_stats()
        except Exception as e:  # pragma: no cover
            self._logger.exception("Error during game end: %s", e)
        finally:
            self.set_hosted(value=False)
            self.state = GameState.ENDED
            self.game_service.mark_dirty(self)

    async def load_results(self):
        """
        Load results from the database
        :return:
        """
        self._results = {}
        async with db.engine.acquire() as conn:
            result = await conn.execute(
                "SELECT `playerId`, `place`, `score` "
                "FROM `game_player_stats` "
                "WHERE `gameId`=%s", (self.id,))

            async for row in result:
                player_id, startspot, score = row[0], row[1], row[2]
                # FIXME: Assertion about startspot == army
                # FIXME: Reporter not retained in database
                await self.add_result(0, startspot, 'score', score)

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
            try:
                score = self.get_army_score(army)
                scores[player] = score
                self._logger.info('Result for army %s, player: %s: %s', army, player, score)
            except KeyError:
                # Default to -1 if there is no result
                scores[player] = -1

        async with db.engine.acquire() as conn:
            rows = []
            for player, score in scores.items():
                self._logger.info("Score for player %s: %s", player, score)
                rows.append((score, self.id, player.id))

            await conn.execute(
                "UPDATE game_player_stats "
                "SET `score`=%s, `scoreTime`=NOW() "
                "WHERE `gameId`=%s AND `playerId`=%s", rows)

    async def clear_data(self):
        async with db.engine.acquire() as conn:
            await conn.execute(
                "DELETE FROM game_player_stats "
                "WHERE gameId=%s", (self.id,))
            await conn.execute(
                "DELETE FROM game_stats "
                "WHERE id=%s", (self.id,))

    async def persist_rating_change_stats(self, rating_groups, rating='global'):
        """
        Persist computed ratings to the respective players' selected rating
        :param rating_groups: of the form returned by Game.compute_rating
        :return: None
        """
        self._logger.info("Saving rating change stats")
        new_ratings = {
            player: new_rating
            for team in rating_groups
            for player, new_rating in team.items()
        }

        rating_table = '{}_rating'.format('ladder1v1' if rating == 'ladder' else rating)

        async with db.engine.acquire() as conn:
            for player, new_rating in new_ratings.items():
                self._logger.debug("New %s rating for %s: %s", rating, player, new_rating)
                setattr(player, '{}_rating'.format(rating), new_rating)
                await conn.execute(
                    "UPDATE game_player_stats "
                    "SET after_mean = %s, after_deviation = %s, scoreTime = NOW() "
                    "WHERE gameId = %s AND playerId = %s",
                    (new_rating.mu, new_rating.sigma, self.id, player.id))
                if rating != 'ladder':
                    player.numGames += 1

                await self._update_rating_table(conn, rating_table, player, new_rating)

                self.game_service.player_service.mark_dirty(player)

    async def _update_rating_table(self, conn, table: str, player: Player, new_rating):
        # If we are updating the ladder1v1_rating table then we also need to update
        # the `winGames` column which doesn't exist on the global_rating table
        if table == 'ladder1v1_rating':
            is_victory = self.outcome(player) == GameOutcome.VICTORY
            await conn.execute(
                "UPDATE ladder1v1_rating "
                "SET mean = %s, is_active=1, deviation = %s, numGames = numGames + 1, winGames = winGames + %s "
                "WHERE id = %s", (new_rating.mu, new_rating.sigma, 1 if is_victory else 0, player.id))
        else:
            await conn.execute(
                "UPDATE " + table + " "
                "SET mean = %s, is_active=1, deviation = %s, numGames = numGames + 1 "
                "WHERE id = %s", (new_rating.mu, new_rating.sigma, player.id))

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

    async def _validate_game_options(self,
                                     valid_options: Dict[str, Tuple[Any, ValidityState]]) -> bool:
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
        if not self.is_even:
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
        assert self.state == GameState.LOBBY
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

        async with db.engine.acquire() as conn:
            # Determine if the map is blacklisted, and invalidate the game for ranking purposes if
            # so, and grab the map id at the same time.
            result = await conn.execute(
                "SELECT id, ranked FROM map_version "
                "WHERE lower(filename) = lower(%s)", (self.map_file_path,))
            row = await result.fetchone()

            if row:
                self.map_id = row['id']

            if (not row or not row['ranked']) and self.validity is ValidityState.VALID:
                await self.mark_invalid(ValidityState.BAD_MAP)

            modId = self.game_service.featured_mods[self.game_mode].id

            # Write out the game_stats record.
            # In some cases, games can be invalidated while running: we check for those cases when
            # the game ends and update this record as appropriate.

            await conn.execute(
                "INSERT INTO game_stats(id, gameType, gameMod, `host`, mapId, gameName, validity)"
                "VALUES(%s, %s, %s, %s, %s, %s, %s)",
                (
                    self.id,
                    str(self.gameOptions.get('Victory').value),
                    modId,
                    self.host.id,
                    self.map_id,
                    self.name,
                    self.validity.value
                )
            )

    async def update_game_player_stats(self):
        query_str = "INSERT INTO `game_player_stats` " \
                    "(`gameId`, `playerId`, `faction`, `color`, `team`, `place`, `mean`, `deviation`, `AI`, `score`) " \
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"

        query_args = []
        for player in self.players:
            player_option = functools.partial(self.get_player_option, player.id)
            options = {key: player_option(key)
                       for key in ['Team', 'StartSpot', 'Color', 'Faction']}

            def is_observer() -> bool:
                return options.get('Team', -1) < 0 or options.get('StartSpot', 0) < 0

            if is_observer():
                continue

            if self.game_mode == 'ladder1v1':
                mean, dev = player.ladder_rating
            else:
                mean, dev = player.global_rating

            query_args.append((
                self.id,
                str(player.id),
                options['Faction'],
                options['Color'],
                options['Team'],
                options['StartSpot'],
                mean, dev, 0, -1
            ))

        async with db.engine.acquire() as conn:
            await conn.execute(query_str, query_args)

    def getGamemodVersion(self):
        return self.game_service.game_mode_versions[self.game_mode]

    def sanitize_name(self, name: str) -> str:
        """
        Replaces sequences of non-latin characters with an underscore and truncates the string to 128 characters
        Avoids the game name to crash the mysql INSERT query by being longer than the column's max size or by
        containing non-latin1 characters
        """
        return re.sub('[^\x20-\xFF]+', '_', name)[0:128]

    async def mark_invalid(self, new_validity_state: ValidityState):
        self._logger.info("Marked as invalid because: %s", repr(new_validity_state))
        self.validity = new_validity_state

        # If we haven't started yet, the invalidity will be persisted to the database when we start.
        # Otherwise, we have to do a special update query to write this information out.
        if self.state != GameState.LIVE:
            return

        # Currently, we can only end up here if a game desynced or was a custom game that terminated
        # too quickly.
        async with db.engine.acquire() as conn:
            await conn.execute(
                "UPDATE game_stats SET validity = %s "
                "WHERE id = %s", (new_validity_state.value, self.id))

    def get_army_score(self, army):
        """
        Since we log multiple results from multiple sources, we have to pick one.

        On conflict we try to pick the most frequently reported score. If there
        are multiple scores with the same number of reports, we pick the greater
        score.

        TODO: Flag games with conflicting scores for manual review.
        :param army index of army
        :raise KeyError
        :return:
        """
        scores: Dict[int, int] = Counter(
            map(lambda res: res[2], self._results.get(army, []))
        )

        # There were no results
        if not scores:
            return 0

        # All scores agreed
        if len(scores) == 1:
            return scores.popitem()[0]

        # Return the highest score with the most votes
        self._logger.info("Conflicting scores (%s) reported for game %s", scores, self)
        score, _votes = max(scores.items(), key=lambda kv: kv[::-1])
        return score

    def get_army_result(self, player):
        results = self._results.get(self.get_player_option(player.id, 'Army'))
        if not results:
            return None

        most_reported_result = Counter(i[1] for i in results).most_common(1)[0]
        outcome = most_reported_result[0]
        return outcome

    def compute_rating(self, rating='global'):
        """
        Compute new ratings
        :param rating: 'global' or 'ladder'
        :return: rating groups of the form:
        >>> p1,p2,p3,p4 = Player()
        >>> [{p1: p1.rating, p2: p2.rating}, {p3: p3.rating, p4: p4.rating}]
        """
        assert self.state == GameState.LIVE or self.state == GameState.ENDED
        team_scores = {}
        ffa_scores = []
        for player in sorted(self.players,
                             key=lambda p: self.get_player_option(p.id, 'Army') or -1):
            team = self.get_player_option(player.id, 'Team')
            army = self.get_player_option(player.id, 'Army')
            if army < 0:
                self._logger.debug("Skipping %s", player)
                continue
            if not team:
                raise GameError("Missing team for player id: {}".format(player.id))
            if team != 1:
                if team not in team_scores:
                    team_scores[team] = 0
                try:
                    team_scores[team] += self.get_army_score(army)
                except KeyError:
                    team_scores[team] += 0
                    self._logger.warning("Missing game result for %s: %s", army, player)
            elif team == 1:
                ffa_scores.append((player, self.get_army_score(army)))
        ranks = [-score for team, score in sorted(team_scores.items(), key=lambda t: t[0])]
        rating_groups = []
        for team in sorted(self.teams):
            if team != 1:
                rating_groups += [{player: Rating(*getattr(player, '{}_rating'.format(rating)))
                                   for player in self.players if
                                   self.get_player_option(player.id, 'Team') == team}]
        for player, score in sorted(ffa_scores, key=lambda x: self.get_player_option(x[0].id, 'Army')):
            rating_groups += [{player: Rating(*getattr(player, '{}_rating'.format(rating)))}]
            ranks.append(-score)
        self._logger.debug("Rating groups: %s", rating_groups)
        self._logger.debug("Ranks: %s", ranks)
        return trueskill.rate(rating_groups, ranks)

    async def report_army_stats(self, stats):
        self._army_stats = stats
        await self._process_pending_army_stats()

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
            "featured_mod_versions": self.getGamemodVersion(),
            "sim_mods": self.mods,
            "mapname": self.map_folder_name,
            "map_file_path": self.map_file_path,
            "host": self.host.login if self.host else '',
            "num_players": len(self.players),
            "max_players": self.max_players,
            "launched_at": self.launched_at,
            "teams": {
                team: [player.login for player in self.players
                       if self.get_player_option(player.id, 'Team') == team]
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
        return "Game({},{},{},{})".format(self.id, self.host.login if self.host else '', self.map_file_path,
                                          len(self.players))
