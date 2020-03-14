import asyncio
from collections import Counter
from typing import Dict, List, Optional, Union, ValuesView

import aiocron
import server.metrics as metrics
from server.core import Service
from server.db import FAFDatabase
from server.decorators import with_logger
from server.games import CoopGame, CustomGame, FeaturedMod, LadderGame
from server.games.game import Game, GameState, VisibilityState
from server.matchmaker import MatchmakerQueue
from server.players import Player


@with_logger
class GameService(Service):
    """
    Utility class for maintaining lifecycle of games
    """
    def __init__(
        self,
        database: FAFDatabase,
        player_service,
        game_stats_service,
    ):
        self._db = database
        self._dirty_games = set()
        self._dirty_queues = set()
        self.player_service = player_service
        self.game_stats_service = game_stats_service
        self.game_id_counter = 0

        # Populated below in really_update_static_ish_data.
        self.featured_mods = dict()

        # A set of mod ids that are allowed in ranked games (everyone loves caching)
        self.ranked_mods = set()

        # The ladder map pool. Each entry is an (id, name, filename) tuple.
        self.ladder_maps = set()

        # Temporary proxy for the ladder service
        self.ladder_service = None

        # The set of active games
        self._games: Dict[int, Game] = dict()

    async def initialize(self):
        await self.initialise_game_counter()
        await self.update_data()
        self._update_cron = aiocron.crontab(
            '*/10 * * * *', func=self.update_data
        )

    async def initialise_game_counter(self):
        async with self._db.acquire() as conn:
            # InnoDB, unusually, doesn't allow insertion of values greater than the next expected
            # value into an auto_increment field. We'd like to do that, because we no longer insert
            # games into the database when they don't start, so game ids aren't contiguous (as
            # unstarted games consume ids that never get written out).
            # So, id has to just be an integer primary key, no auto-increment: we handle its
            # incrementing here in game service, but have to do this slightly expensive query on
            # startup (though the primary key index probably makes it super fast anyway).
            # This is definitely a better choice than inserting useless rows when games are created,
            # doing LAST_UPDATE_ID to get the id number, and then doing an UPDATE when the actual
            # data to go into the row becomes available: we now only do a single insert for each
            # game, and don't end up with 800,000 junk rows in the database.
            result = await conn.execute("SELECT MAX(id) FROM game_stats")
            row = await result.fetchone()
            self.game_id_counter = row[0]

    async def update_data(self):
        """
        Loads from the database the mostly-constant things that it doesn't make sense to query every
        time we need, but which can in principle change over time.
        """
        async with self._db.acquire() as conn:
            result = await conn.execute("SELECT `id`, `gamemod`, `name`, description, publish, `order` FROM game_featuredMods")

            async for row in result:
                mod_id, name, full_name, description, publish, order = (row[i] for i in range(6))
                self.featured_mods[name] = FeaturedMod(
                    mod_id, name, full_name, description, publish, order)

            result = await conn.execute("SELECT uid FROM table_mod WHERE ranked = 1")
            rows = await result.fetchall()

            # Turn resultset into a list of uids
            self.ranked_mods = set(map(lambda x: x[0], rows))

            # Load all ladder maps
            result = await conn.execute(
                "SELECT ladder_map.idmap, "
                "table_map.name, "
                "table_map.filename "
                "FROM ladder_map "
                "INNER JOIN table_map ON table_map.id = ladder_map.idmap")
            self.ladder_maps = [(row[0], row[1], row[2]) async for row in result]

    @property
    def dirty_games(self):
        return self._dirty_games

    @property
    def dirty_queues(self):
        return self._dirty_queues

    def mark_dirty(self, obj: Union[Game, MatchmakerQueue]):
        if isinstance(obj, Game):
            self._dirty_games.add(obj)
        elif isinstance(obj, MatchmakerQueue):
            self._dirty_queues.add(obj)

    def clear_dirty(self):
        self._dirty_games = set()
        self._dirty_queues = set()

    def create_uid(self) -> int:
        self.game_id_counter += 1

        return self.game_id_counter

    def create_game(
        self,
        game_mode: str,
        visibility=VisibilityState.PUBLIC,
        host: Optional[Player] = None,
        name: Optional[str] = None,
        mapname: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Main entrypoint for creating new games
        """
        game_id = self.create_uid()
        args = {
            "database": self._db,
            "id_": game_id,
            "host": host,
            "name": name,
            "map_": mapname,
            "game_mode": game_mode,
            "game_service": self,
            "game_stats_service": self.game_stats_service
        }

        game_class = {
            'ladder1v1':    LadderGame,
            'coop':         CoopGame,
            'faf':          CustomGame,
            'fafbeta':      CustomGame,
            'equilibrium':  CustomGame
        }.get(game_mode, Game)
        game = game_class(**args)

        self._games[game_id] = game

        game.visibility = visibility
        game.password = password

        self.mark_dirty(game)
        return game

    def update_active_game_metrics(self):
        modes = list(self.featured_mods.keys())

        game_counter = Counter(
            (
                game.game_mode if game.game_mode in modes else "other",
                game.state
            )
            for game in self._games.values()
        )

        for state in GameState:
            for mode in modes + ["other"]:
                metrics.active_games.labels(mode, state.name).set(
                    game_counter[(mode, state)]
                )

    @property
    def live_games(self) -> List[Game]:
        return [game for game in self._games.values()
                if game.state is GameState.LIVE]

    @property
    def open_games(self) -> List[Game]:
        """
        Return all games that meet the client's definition of "not closed".
        Server game states are mapped to client game states as follows:

            GameState.LOBBY: 'open',
            GameState.LIVE: 'playing',
            GameState.ENDED: 'closed',
            GameState.INITIALIZING: 'closed',

        The client ignores everything "closed". This property fetches all such not-closed games.
        :return:
        """
        return [game for game in self._games.values()
                if game.state is GameState.LOBBY or game.state is GameState.LIVE]

    @property
    def all_games(self) -> ValuesView[Game]:
        return self._games.values()

    @property
    def pending_games(self) -> List[Game]:
        return [game for game in self._games.values()
                if game.state is GameState.LOBBY or game.state is GameState.INITIALIZING]

    def remove_game(self, game: Game):
        if game.id in self._games:
            del self._games[game.id]

    def __getitem__(self, item: int) -> Game:
        return self._games[item]

    def __contains__(self, item):
        return item in self._games
