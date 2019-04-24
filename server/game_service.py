import asyncio
from typing import Dict, List, Optional, Union, ValuesView

import aiocron
import server.db as db
from server import GameState, VisibilityState
from server.decorators import with_logger
from server.games import CoopGame, CustomGame, FeaturedMod, LadderGame
from server.games.game import Game
from server.matchmaker import MatchmakerQueue
from server.players import Player


@with_logger
class GameService:
    """
    Utility class for maintaining lifecycle of games
    """
    def __init__(self, player_service, game_stats_service):
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
        self.games: Dict[int, Game] = dict()

        # Cached versions for files by game_mode ( featured mod name )
        # For use by the patcher
        self.game_mode_versions = dict()

        # Synchronously initialise the game-id counter and static-ish-data.
        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.ensure_future(self.initialise_game_counter()))
        loop.run_until_complete(loop.create_task(self.update_data()))
        self._update_cron = aiocron.crontab('*/10 * * * *', func=self.update_data)

    async def initialise_game_counter(self):
        async with db.engine.acquire() as conn:
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
        async with db.engine.acquire() as conn:
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

            for mod in self.featured_mods.values():
                self._logger.debug("Loading featuredMod %s", mod.name)
                if mod.name == 'ladder1v1':
                    continue
                self.game_mode_versions[mod.name] = {}
                t = "updates_{}".format(mod.name)
                tfiles = t + "_files"
                result = await conn.execute(
                    "SELECT %s.fileId, MAX(%s.version) "
                    "FROM %s LEFT JOIN %s ON %s.fileId = %s.id "
                    "GROUP BY %s.fileId" % (tfiles, tfiles, tfiles, t, tfiles, t, tfiles))

                async for row in result:
                    fileId, version = row[0], row[1]
                    self.game_mode_versions[mod.name][fileId] = version
            # meh
            self.game_mode_versions['ladder1v1'] = self.game_mode_versions['faf']

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
        host: Optional[Player]=None,
        name: Optional[str]=None,
        mapname: Optional[str]=None,
        password: Optional[str]=None
    ):
        """
        Main entrypoint for creating new games
        """
        game_id = self.create_uid()
        args = {
            "id_": game_id,
            "host": host,
            "name": name,
            "map_": mapname,
            "game_mode": game_mode,
            "game_service": self,
            "game_stats_service": self.game_stats_service
        }

        GameClass = {
            'ladder1v1':    LadderGame,
            'coop':         CoopGame,
            'faf':          CustomGame,
            'fafbeta':      CustomGame,
            'equilibrium':  CustomGame
        }.get(game_mode, Game)
        game = GameClass(**args)

        self.games[game_id] = game

        game.visibility = visibility
        game.password = password

        self.mark_dirty(game)
        return game

    @property
    def live_games(self) -> List[Game]:
        return [game for game in self.games.values()
                if game.state == GameState.LIVE]

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
        return [game for game in self.games.values()
                if game.state == GameState.LOBBY or game.state == GameState.LIVE]

    @property
    def all_games(self) -> ValuesView[Game]:
        return self.games.values()

    @property
    def pending_games(self) -> List[Game]:
        return [game for game in self.games.values()
                if game.state == GameState.LOBBY or game.state == GameState.INITIALIZING]

    def remove_game(self, game: Game):
        if game.id in self.games:
            del self.games[game.id]

    def all_game_modes(self):
        mods = []
        for name, mod in self.featured_mods.items():
            mods.append({
                'command': 'mod_info',
                'publish': mod.publish,
                'name': name,
                'order': mod.order,
                'fullname': mod.full_name,
                'desc': mod.description
            })
        return mods

    def __getitem__(self, item: int) -> Game:
        return self.games[item]

    def __contains__(self, item):
        return item in self.games
