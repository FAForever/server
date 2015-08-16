import asyncio
import aiocron
import aiomysql
from server import games

import server.db as db
from server import games
from server.decorators import with_logger
from server.games.game import Game
from server.players import Player
from passwords import DB_NAME

@with_logger
class GameService:
    """
    Utility class for maintaining lifecycle of games
    """
    def __init__(self, players):
        self._dirty_games = set()
        self.players = players
        self.game_id_counter = 0

        # Populated below in really_update_static_ish_data.
        self.featured_mods = dict()

        # A set of mod ids that are allowed in ranked games (everyone loves caching)
        self.ranked_mods = set()

        # The ladder map pool. Each entry is an (id, name) tuple.
        self.ladder_maps = set()

        # Synchronously initialise the game-id counter and static-ish-data.
        asyncio.get_event_loop().run_until_complete(asyncio.async(self.initialise_game_counter()))
        asyncio.get_event_loop().run_until_complete(asyncio.async(self.really_update_static_ish_data()))

        self._containers = {}
        self.add_game_modes()

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
            cursor = yield from conn.cursor(aiomysql.DictCursor)

            # Load the featured mods table into memory (the bits of it we care about).
            featured_mods = dict()

            yield from cursor.execute("SELECT id, gamemod, description, name FROM game_featuredMods")

            for i in range(0, cursor.rowcount):
                row = yield from cursor.fetchone()
                featured_mods[row["gamemod"]] = row

            self.featured_mods = featured_mods

            # Get an ordinary cursor back.
            cursor = yield from conn.cursor()
            yield from cursor.execute("SELECT id FROM table_mod WHERE ranked = 1")

            # Turn resultset into a list of ids
            rows = yield from cursor.fetchall()
            self.ranked_mods = set(map(lambda x: x[0], rows))

            # Load all ladder maps
            yield from cursor.execute("SELECT ladder_map.idmap, table_map.name FROM ladder_map INNER JOIN table_map ON table_map.id = ladder_map.idmap")
            self.ladder_maps = yield from cursor.fetchall()

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

    def add_game_modes(self):
        for name, nice_name, container in games.game_modes:
            if name not in self.featured_mods:
                continue
            mode_description = self.featured_mods[name]['description']

            self._containers[name] = container(name=name,
                                               desc=mode_description,
                                               nice_name=nice_name,
                                               db=self.db,
                                               games_service=self)

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
        game = Game(self.createUuid(), self, host, name, mapname)
        game.game_mode = game_mode
        self._containers[game_mode].addGame(game)

        self._logger.info("{} created in {} container".format(game, game_mode))
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
    def active_games(self):
        games = []
        for c, g in self._containers.items():
            games += g.games
        return games

    def remove_game(self, game: Game):
        for c, g in self._containers.items():
            if game in g.games:
                g.games.remove(game)

    def all_game_modes(self):
        modes = []
        for c, g in self._containers.items():
            modes.append({
                'command': 'mod_info',
                'name': g.game_mode,
                'fullname': g.gameNiceName,
                'icon': None,
                'host': g.host,
                'join': g.join,
                'live': g.live,
                'desc': g.desc,
                'options': []
            })
        return modes

    def find_by_id(self, id: int):
        """
        Look up a game by ID
        :rtype: Game
        """
        for container in self._containers:
            game = self._containers[container].findGameById(id)
            if game is not None:
                return game
