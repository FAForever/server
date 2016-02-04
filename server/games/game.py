from functools import partial
from enum import IntEnum, unique
import logging
import time
import functools
import asyncio
from typing import Union
import trueskill
from trueskill import Rating
import server.db as db
from server.abc.base_game import GameConnectionState, BaseGame, InitMode
from server.players import Player, PlayerState


@unique
class GameState(IntEnum):
    INITIALIZING = 0
    LOBBY = 1
    LIVE = 2
    ENDED = 3


@unique
class Victory(IntEnum):
    DEMORALIZATION = 0
    DOMINATION = 1
    ERADICATION = 2
    SANDBOX = 3

    @staticmethod
    def from_gpgnet_string(value):
        if value == "demoralization":
            return Victory.DEMORALIZATION
        elif value == "domination":
            return Victory.DOMINATION
        elif value == "eradication":
            return Victory.ERADICATION
        elif value == "sandbox":
            return Victory.SANDBOX


@unique
class VisibilityState(IntEnum):
    PUBLIC = 0
    FRIENDS = 1

    @staticmethod
    def from_string(value):
        if value == "public":
            return VisibilityState.PUBLIC
        elif value == "friends":
            return VisibilityState.FRIENDS

    @staticmethod
    def to_string(value):
        if value == VisibilityState.PUBLIC:
            return "public"
        elif value == VisibilityState.FRIENDS:
            return "friends"


# Identifiers must be kept in sync with the contents of the invalid_game_reasons table.
# New reasons added should have a description added to that table. Identifiers should never be
# reused, and values should never be deleted from invalid_game_reasons.
class ValidityState(IntEnum):
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


class GameError(Exception):
    pass


class Game(BaseGame):
    """
    Object that lasts for the lifetime of a game on FAF.
    """
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, id, game_service, game_stats_service,
                 host=None,
                 name='None',
                 map='SCMP_007',
                 game_mode='faf'):
        """
        Initializes a new game
        :type id int
        :type name: str
        :type map: str
        :return: Game
        """
        super().__init__()
        self._results = {}
        self._army_stats = None
        self._players_with_unsent_army_stats = []
        self._game_stats_service = game_stats_service
        self.game_service = game_service
        self._player_options = {}
        self.launched_at = None
        self._logger = logging.getLogger("{}.{}".format(self.__class__.__qualname__, id))
        self.id = id
        self.visibility = VisibilityState.PUBLIC
        self.max_players = 12
        self.host = host
        self.name = name
        self.map_id = 0
        self.map_file_path = map
        self.password = None
        self._players = []
        self.gameType = 0
        self.AIs = {}
        self.desyncs = 0
        self.validity = ValidityState.VALID
        self.game_mode = game_mode
        self.state = GameState.INITIALIZING
        self._connections = {}
        self.gameOptions = {'FogOfWar': 'explored',
                            'GameSpeed': 'normal',
                            'Victory': Victory.from_gpgnet_string('demoralization'),
                            'CheatsEnabled': 'false',
                            'PrebuiltUnits': 'Off',
                            'NoRushOption': 'Off',
                            'RestrictedCategories': 0}

        self.mods = []
        self._logger.info("{} created".format(self))
        asyncio.get_event_loop().call_later(20, self.timeout_game)

    def timeout_game(self):
        if self.state == GameState.INITIALIZING:
            self.state = GameState.ENDED

    @property
    def armies(self):
        return frozenset({self.get_player_option(player.id, 'Army')
                          for player in self.players})

    @property
    def is_mutually_agreed_draw(self):
        for army in self.armies:
            if army in self._results:
                for result in self._results[army]:
                    if result[2] != 'mutual_draw':
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
            return frozenset(self._players)

    @property
    def connections(self):
        return self._connections.values()

    @property
    def teams(self):
        return frozenset({self.get_player_option(player.id, 'Team')
                          for player in self.players})

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
                "Ignoring results for unknown army {}: {} {} reported by: {}".format(army, result_type, score,
                                                                                     reporter))
            return

        if army not in self._results:
            self._results[army] = []
        self._logger.info("{} reported result for army {}: {} {}".format(reporter, army, result_type, score))
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
        if self._army_stats is None or self.gameOptions["CheatsEnabled"] != "false":
            return

        self._players_with_unsent_army_stats.remove(player)
        await self._game_stats_service.process_game_stats(player, self, self._army_stats)

    def add_game_connection(self, game_connection):
        """
        Add a game connection to this game
        :param game_connection:
        :return:
        """
        if game_connection.state != GameConnectionState.CONNECTED_TO_HOST:
            raise GameError("Invalid GameConnectionState: {}".format(game_connection.state))
        if self.state != GameState.LOBBY:
            raise GameError("Invalid GameState: {state}".format(state=self.state))
        self._logger.info("Added game connection {}".format(game_connection))
        self._connections[game_connection.player] = game_connection

    async def remove_game_connection(self, game_connection):
        """
        Remove a game connection from this game

        Will trigger on_game_end if there are no more active connections to the game
        :param peer:
        :param
        :return: None
        """
        if game_connection in self._connections.values():
            del self._connections[game_connection.player]
        if game_connection.player:
            del game_connection.player.game
        self._logger.info("Removed game connection {}".format(game_connection))

        if len(self._connections) == 0 or self.host == game_connection.player:
            await self.on_game_end()
        else:
            await self._process_pending_army_stats()

    async def on_game_end(self):
        if self.state == GameState.LOBBY:
            self._logger.info("Game cancelled pre launch")
        elif self.state == GameState.INITIALIZING:
            self._logger.info("Game cancelled pre initialization")
        elif self.state == GameState.LIVE:
            self._logger.info("Game finished normally")

            if self.desyncs > 20:
                await self.mark_invalid(ValidityState.TOO_MANY_DESYNCS)

            if time.time() - self.launched_at > 4*60 and self.is_mutually_agreed_draw:
                self._logger.info("Game is a mutual draw")
                await self.mark_invalid(ValidityState.MUTUAL_DRAW)

            await self.persist_results()
            await self.rate_game()

            for player in self._players_with_unsent_army_stats:
                await self._process_army_stats_for_player(player)
        self.state = GameState.ENDED

    async def load_results(self):
        """
        Load results from the database
        :return:
        """
        self._results = {}
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()
            await cursor.execute("SELECT `playerId`, `place`, `score` "
                                 "FROM `game_player_stats` "
                                 "WHERE `gameId`=%s", (self.id,))
            results = await cursor.fetchall()
            for player_id, startspot, score in results:
                # FIXME: Assertion about startspot == army
                # FIXME: Reporter not retained in database
                await self.add_result(0, startspot, 'score', score)

    async def persist_results(self):
        """
        Persist game results into the database

        Requires the game to have been launched and the appropriate rows to exist in the database.
        :return:
        """

        self._logger.info("Saving game scores")
        results = {}
        for player in self.players:
            army = self.get_player_option(player.id, 'Army')
            try:
                result = self.get_army_result(army)
                results[player] = result
                self._logger.info('Result for army {}: {}'.format(army, result))
            except KeyError:
                # Default to -1 if there is no result
                results[player] = -1

        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            rows = []
            for player, result in results.items():
                self._logger.info("Result for player {}: {}".format(player, result))
                rows.append((player.id, result, self.id))

            await cursor.executemany("UPDATE game_player_stats "
                                     "SET `playerId`=%s, `score`=%s, `scoreTime`=NOW() "
                                     "WHERE `gameId`=%s", rows)

    async def clear_data(self):
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()
            await cursor.execute("DELETE FROM game_player_stats "
                                 "WHERE gameId=%s", (self.id,))
            await cursor.execute("DELETE FROM game_stats "
                                 "WHERE id=%s", (self.id,))

    @asyncio.coroutine
    def persist_rating_change_stats(self, rating_groups, rating='global'):
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

        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()

            for player, new_rating in new_ratings.items():
                yield from cursor.execute("UPDATE game_player_stats "
                                          "SET after_mean = ?, after_deviation = ?, scoreTime = NOW() "
                                          "WHERE gameId = ? AND playerId = ?", new_rating.mu, new_rating.sigma, self.id,
                                          player.id)

                yield from cursor.execute("UPDATE {}_rating "
                                          "SET mean = ?, is_active=1, deviation = ?, numGames = (numGames + 1) "
                                          "WHERE id = ?".format(rating), new_rating.mu, new_rating.sigma, player.id)

    def set_player_option(self, id, key, value):
        """
        Set game-associative options for given player, by id
        :param id: int
        :type id: int
        :param key: option key string
        :type key: str
        :param value: option value
        :return: None
        """
        if id not in self._player_options:
            self._player_options[id] = {}
        self._player_options[id][key] = value

    def get_player_option(self, id, key):
        """
        Retrieve game-associative options for given player, by their uid
        :param id:
        :type id: int
        :param key:
        :return:
        """
        try:
            return self._player_options[id][key]
        except KeyError:
            return None

    def set_ai_option(self, name, key, value):
        """
        This is a noop for now
        :param name: Name of the AI
        :param key: option key string
        :param value: option value
        :return:
        """
        if not name in self.AIs:
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
        for id in self.mods:
            if id not in self.game_service.ranked_mods:
                await self.mark_invalid(ValidityState.BAD_MOD)
                break

        if self.gameOptions['Victory'] != Victory.DEMORALIZATION and self.game_mode != 'coop':
            await self.mark_invalid(ValidityState.WRONG_VICTORY_CONDITION)

        elif self.gameOptions["FogOfWar"] != "explored":
            await self.mark_invalid(ValidityState.NO_FOG_OF_WAR)

        elif self.gameOptions["CheatsEnabled"] != "false":
            await self.mark_invalid(ValidityState.CHEATS_ENABLED)

        elif self.gameOptions["PrebuiltUnits"] != "Off":
            await self.mark_invalid(ValidityState.PREBUILT_ENABLED)

        elif self.gameOptions["NoRushOption"] != "Off":
            await self.mark_invalid(ValidityState.NORUSH_ENABLED)

        elif self.gameOptions["RestrictedCategories"] != 0:
            await self.mark_invalid(ValidityState.BAD_UNIT_RESTRICTIONS)

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
        await self.validate_game_settings()
        await self.on_game_launched()

    async def on_game_launched(self):
        for player in self.players:
            player.state = PlayerState.PLAYING
        await self.update_ratings()
        await self.update_game_stats()
        await self.update_game_player_stats()

    async def update_game_stats(self):
        """
        Runs at game-start to populate the game_stats table (games that start are ones we actually
        care about recording stats for, after all).
        """
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            # Determine if the map is blacklisted, and invalidate the game for ranking purposes if
            # so, and grab the map id at the same time.
            await cursor.execute("SELECT table_map.id, table_map_unranked.id "
                                 "FROM table_map LEFT JOIN table_map_unranked "
                                 "ON table_map.id = table_map_unranked.id "
                                 "WHERE table_map.filename = %s", (self.map_file_path,))
            result = await cursor.fetchone()
            if result:
                (self.map_id, blacklist_flag) = result

                if blacklist_flag:
                    await self.mark_invalid(ValidityState.BAD_MAP)

            modId = self.game_service.featured_mods[self.game_mode].id

            # Write out the game_stats record.
            # In some cases, games can be invalidated while running: we check for those cases when
            # the game ends and update this record as appropriate.
            await cursor.execute("INSERT INTO game_stats(id, gameType, gameMod, `host`, mapId, gameName, validity)"
                                 "VALUES(%s, %s, %s, %s, %s, %s, %s)",
                                 (self.id,
                                  str(self.gameOptions.get('Victory').value),
                                  modId,
                                  self.host.id,
                                  self.map_id,
                                  self.name,
                                  self.validity.value))

    async def update_game_player_stats(self):
        query_str = "INSERT INTO `game_player_stats` " \
                    "(`gameId`, `playerId`, `faction`, `color`, `team`, `place`, `mean`, `deviation`, `AI`, `score`) " \
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"

        query_args = []
        for player in self.players:
            player_option = functools.partial(self.get_player_option, player.id)
            options = {key: player_option(key)
                       for key in ['Team', 'StartSpot', 'Color', 'Faction']}

            if options['Team'] > 0 and options['StartSpot'] >= 0:
                if self.game_mode == 'ladder1v1':
                    mean, dev = player.ladder_rating
                else:
                    mean, dev = player.global_rating

                query_args.append((self.id,
                                   str(player.id),
                                   options['Faction'],
                                   options['Color'],
                                   options['Team'],
                                   options['StartSpot'],
                                   mean,
                                   dev,
                                   0,
                                   -1))

        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            await cursor.executemany(query_str, query_args)

    def getGamemodVersion(self):
        return self.game_service.game_mode_versions[self.game_mode]

    async def mark_invalid(self, new_validity_state: ValidityState):
        self._logger.info("marked as invalid because: {}".format(repr(new_validity_state)))
        self.validity = new_validity_state

        # If we haven't started yet, the invalidity will be persisted to the database when we start.
        # Otherwise, we have to do a special update query to write this information out.
        if self.state == GameState.LOBBY:
            return

        # Currently, we can only end up here if a game desynced or was a custom game that terminated
        # too quickly.
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            await cursor.execute("UPDATE game_stats "
                                 "SET validity = %s "
                                 "WHERE id = %s", (new_validity_state.value, self.id))

    def get_army_result(self, army):
        """
        Since we log multiple results from multiple sources, we have to pick one.

        We're optimistic and simply choose the highest reported score.

        TODO: Flag games with conflicting scores for manual review.
        :param army index of army
        :raise KeyError
        :return:
        """
        score = 0
        for result in self._results[army]:
            score = max(score, result[2])
        return score

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
        for player in self.players:
            team = self.get_player_option(player.id, 'Team')
            army = self.get_player_option(player.id, 'Army')
            if not team:
                raise GameError("Missing team for player id: {}".format(player.id))
            if team not in team_scores:
                team_scores[team] = []
            try:
                team_scores[team] += [self.get_army_result(army)]
            except KeyError:
                team_scores[team] += [0]
                self._logger.info("Missing game result for {army}: {player}".format(army=army,
                                                                                    player=player))
        ranks = [score for team, score in sorted(team_scores.items())]
        rating_groups = []
        for team in sorted(self.teams):
            rating_groups += [{player: Rating(*getattr(player, '{}_rating'.format(rating)))
                               for player in self.players if
                               self.get_player_option(player.id, 'Team') == team}]
        return trueskill.rate(rating_groups, ranks)

    async def update_ratings(self):
        """ Update all scores from the DB before updating the results"""
        self._logger.debug("updating ratings")

        player_ids = list(map(lambda p: p.id, self.players))

        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            await cursor.execute("SELECT `id`, `mean`, `deviation` "
                                 "FROM `global_rating` "
                                 "WHERE `id` IN %s", (player_ids,))

            rows = await cursor.fetchall()
            for row in rows:
                (player_id, mean, deviation) = row

                self.game_service.player_service[player_id].global_rating = (mean, deviation)

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
            "mapname": (self.map_file_path or "").lower(),
            "host": self.host.login if self.host else '',
            "num_players": len(self.players),
            "game_type": self.gameType,
            "max_players": self.max_players,
            "launched_at": self.launched_at,
            "teams": {
                team: [player.login for player in self.players
                       if self.get_player_option(player.id, 'Team') == team]
                for team in self.teams
                }
        }

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
