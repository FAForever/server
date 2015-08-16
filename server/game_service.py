import asyncio
import aiocron
import aiomysql

import server.db as db
from server import games, GameState
from server.decorators import with_logger
from server.games import FeaturedMod
from server.games.game import Game
from server.players import Player
from passwords import DB_NAME

@with_logger
class GameService:
    """
    Utility class for maintaining lifecycle of games
    """
    def __init__(self, player_service):
        self._dirty_games = set()
        self.player_service = player_service
        self.game_id_counter = 0

        # Populated below in really_update_static_ish_data.
        self.featured_mods = dict()

        # A set of mod ids that are allowed in ranked games (everyone loves caching)
        self.ranked_mods = set()

        # The ladder map pool. Each entry is an (id, name) tuple.
        self.ladder_maps = set()

        # The set of active games
        self.games = dict()

        # Cached versions for files by game_mode ( featured mod name )
        # For use by the patcher
        self.game_mode_versions = dict()

        # Synchronously initialise the game-id counter and static-ish-data.
        asyncio.get_event_loop().run_until_complete(asyncio.async(self.initialise_game_counter()))
        asyncio.get_event_loop().run_until_complete(asyncio.async(self.really_update_static_ish_data()))

        self._containers = {}

    @asyncio.coroutine
    def initialise_game_counter(self):
        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()

            yield from cursor.execute("SELECT AUTO_INCREMENT FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '%s' AND TABLE_NAME = 'game_stats';" % DB_NAME)
            (self.game_id_counter, ) = yield from cursor.fetchone()

    def really_update_static_ish_data(self):
        """
        Loads from the database the mostly-constant things that it doesn't make sense to query every
        time we need, but which can in principle change over time.
        """
        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()

            yield from cursor.execute("SELECT gamemod, `name`, description, publish FROM game_featuredMods")

            for i in range(0, cursor.rowcount):
                name, full_name, description, publish = yield from cursor.fetchone()
                self.featured_mods[name] = FeaturedMod(name, full_name, description, publish)

            yield from cursor.execute("SELECT id FROM table_mod WHERE ranked = 1")

            # Turn resultset into a list of ids
            rows = yield from cursor.fetchall()
            self.ranked_mods = set(map(lambda x: x[0], rows))

            # Load all ladder maps
            yield from cursor.execute("SELECT ladder_map.idmap, table_map.name FROM ladder_map INNER JOIN table_map ON table_map.id = ladder_map.idmap")
            self.ladder_maps = yield from cursor.fetchall()

            for mod in self.featured_mods.values():
                if mod.name == 'ladder1v1':
                    continue
                self.game_mode_versions[mod.name] = {}
                t = "updates_{}".format(mod.name)
                tfiles = t + "_files"
                yield from cursor.execute("SELECT %s.fileId, MAX(%s.version) "
                                          "FROM %s LEFT JOIN %s ON %s.fileId = %s.id "
                                          "GROUP BY %s.fileId" % (tfiles, tfiles, tfiles, t, tfiles, t, tfiles))
                rows = yield from cursor.fetchall()
                for fileId, version in rows:
                    self.game_mode_versions[mod.name][fileId] = version
            # meh
            self.game_mode_versions['ladder1v1'] = self.game_mode_versions['faf']

    @aiocron.crontab('0 * * * *')
    @asyncio.coroutine
    def update_static_ish_data(self):
        self.really_update_static_ish_data()

    @property
    def dirty_games(self):
        return self._dirty_games

    def mark_dirty(self, game):
        self._dirty_games.add(game)

    def clear_dirty(self):
        self._dirty_games = set()

    # This is still used by ladderGamesContainer: refactoring to make this interaction less
    # ugly would be nice.
    def createUuid(self):
        self.game_id_counter += 1

        return self.game_id_counter - 1

    def create_game(self,
                    visibility: str='public',
                    game_mode: str=None,
                    host: Player=None,
                    name: str=None,
                    mapname: str=None,
                    password: str=None):
        """
        Main entrypoint for creating new games
        """
        id = self.createUuid()
        game = Game(id, self, host, name, mapname, game_mode=game_mode)
        self.games[id] = game

        self._logger.info("{} created".format(game))
        game.access = visibility

        if password is not None:
            game.password = password

        self.mark_dirty(game)
        return game

    def getContainer(self, name):
        if name in self._containers:
            return self._containers[name]
        return None

    @property
    def live_games(self):
        return [game for game in self.games.values()
                if game.state == GameState.LIVE]

    @property
    def pending_games(self):
        return [game for game in self.games.values()
                if game.state == GameState.LOBBY or game.state == GameState.INITIALIZING]

    def remove_game(self, game: Game):
        for c, g in self._containers.items():
            if game in g.games:
                g.games.remove(game)

    def all_game_modes(self):
        mods = []
        for name, mod in self.featured_mods.items():
            mods.append({
                'command': 'mod_info',
                'name': name,
                'fullname': mod.full_name,
                'icon': None,
                'desc': mod.description
            })
        return mods

    def __getitem__(self, item):
        return self.games[item]

    def find_by_id(self, id: int):
        """
        Look up a game by ID
        :rtype: Game
        """
        for container in self._containers:
            game = self._containers[container].findGameById(id)
            if game is not None:
                return game
