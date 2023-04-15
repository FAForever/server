"""
Manages the lifecycle of active games
"""

import asyncio
from collections import Counter
from typing import Optional, Union, ValuesView

import aiocron
from sqlalchemy import select

from server.config import config

from . import metrics
from .core import Service
from .db import FAFDatabase
from .db.models import game_featuredMods
from .decorators import with_logger
from .exceptions import DisabledError
from .games import (
    CustomGame,
    FeaturedMod,
    Game,
    GameState,
    ValidityState,
    VisibilityState
)
from .games.typedefs import EndedGameInfo
from .matchmaker import MatchmakerQueue
from .message_queue_service import MessageQueueService
from .players import Player
from .rating_service import RatingService


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
        rating_service: RatingService,
        message_queue_service: MessageQueueService
    ):
        self._db = database
        self._dirty_games: set[Game] = set()
        self._dirty_queues: set[MatchmakerQueue] = set()
        self.player_service = player_service
        self.game_stats_service = game_stats_service
        self._rating_service = rating_service
        self._message_queue_service = message_queue_service
        self.game_id_counter = 0
        self._allow_new_games = False
        self._drain_event = None

        # Populated below in really_update_static_ish_data.
        self.featured_mods = dict()

        # A set of mod ids that are allowed in ranked games
        self.ranked_mods: set[str] = set()

        # The set of active games
        self._games: dict[int, Game] = dict()

    async def initialize(self) -> None:
        await self.initialise_game_counter()
        await self.update_data()
        self._update_cron = aiocron.crontab(
            "*/10 * * * *", func=self.update_data
        )
        self._allow_new_games = True

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
            sql = "SELECT MAX(id) FROM game_stats"
            self.game_id_counter = await conn.scalar(sql) or 0

    async def update_data(self):
        """
        Loads from the database the mostly-constant things that it doesn't make sense to query every
        time we need, but which can in principle change over time.
        """
        async with self._db.acquire() as conn:
            rows = await conn.execute(select(
                game_featuredMods.c.id,
                game_featuredMods.c.gamemod,
                game_featuredMods.c.name,
                game_featuredMods.c.description,
                game_featuredMods.c.publish,
                game_featuredMods.c.order
            ).select_from(game_featuredMods))

            for row in rows:
                self.featured_mods[row.gamemod] = FeaturedMod(
                    row.id,
                    row.gamemod,
                    row.name,
                    row.description,
                    row.publish,
                    row.order
                )

            result = await conn.execute("SELECT uid FROM table_mod WHERE ranked = 1")

            # Turn resultset into a list of uids
            self.ranked_mods = {row.uid for row in result}

    def mark_dirty(self, obj: Union[Game, MatchmakerQueue]):
        if isinstance(obj, Game):
            self._dirty_games.add(obj)
        elif isinstance(obj, MatchmakerQueue):
            self._dirty_queues.add(obj)

    def pop_dirty_games(self) -> set[Game]:
        dirty_games = self._dirty_games
        self._dirty_games = set()

        return dirty_games

    def pop_dirty_queues(self) -> set[MatchmakerQueue]:
        dirty_queues = self._dirty_queues
        self._dirty_queues = set()

        return dirty_queues

    def create_uid(self) -> int:
        self.game_id_counter += 1

        return self.game_id_counter

    def create_game(
        self,
        game_mode: str,
        game_class: type[Game] = CustomGame,
        visibility=VisibilityState.PUBLIC,
        host: Optional[Player] = None,
        name: Optional[str] = None,
        mapname: Optional[str] = None,
        password: Optional[str] = None,
        matchmaker_queue_id: Optional[int] = None,
        **kwargs
    ):
        """
        Main entrypoint for creating new games
        """
        if not self._allow_new_games:
            raise DisabledError()

        game_id = self.create_uid()
        game_args = {
            "database": self._db,
            "id_": game_id,
            "host": host,
            "name": name,
            "map_": mapname,
            "game_mode": game_mode,
            "game_service": self,
            "game_stats_service": self.game_stats_service,
            "matchmaker_queue_id": matchmaker_queue_id,
        }
        game_args.update(kwargs)
        game = game_class(**game_args)

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

        rating_type_counter = Counter(
            (
                game.rating_type,
                game.state
            )
            for game in self._games.values()
        )

        for state in GameState:
            for rating_type in rating_type_counter.keys():
                metrics.active_games_by_rating_type.labels(rating_type, state.name).set(
                    rating_type_counter[(rating_type, state)]
                )

    @property
    def live_games(self) -> list[Game]:
        return [game for game in self._games.values()
                if game.state is GameState.LIVE]

    @property
    def open_games(self) -> list[Game]:
        """
        Return all games that meet the client's definition of "not closed".
        Server game states are mapped to client game states as follows:

            GameState.LOBBY: "open",
            GameState.LIVE: "playing",
            GameState.ENDED: "closed",
            GameState.INITIALIZING: "closed",

        The client ignores everything "closed". This property fetches all such not-closed games.
        """
        return [game for game in self._games.values()
                if game.state is GameState.LOBBY or game.state is GameState.LIVE]

    @property
    def all_games(self) -> ValuesView[Game]:
        return self._games.values()

    @property
    def pending_games(self) -> list[Game]:
        return [game for game in self._games.values()
                if game.state is GameState.LOBBY or game.state is GameState.INITIALIZING]

    def remove_game(self, game: Game):
        if game.id in self._games:
            self._logger.debug("Removing game %s", game)
            del self._games[game.id]

        if (
            self._drain_event is not None
            and not self._drain_event.is_set()
            and not self._games
        ):
            self._drain_event.set()

    def __getitem__(self, item: int) -> Game:
        return self._games[item]

    def __contains__(self, item):
        return item in self._games

    async def publish_game_results(self, game_results: EndedGameInfo):
        result_dict = game_results.to_dict()
        await self._message_queue_service.publish(
            config.MQ_EXCHANGE_NAME,
            "success.gameResults.create",
            result_dict,
        )

        if (
            game_results.validity is ValidityState.VALID
            and game_results.rating_type is not None
        ):
            metrics.rated_games.labels(game_results.rating_type).inc()
            # TODO: Remove when rating service starts listening to message queue
            await self._rating_service.enqueue(result_dict)

    async def drain_games(self):
        """
        Wait for all games to finish.
        """
        if not self._games:
            return

        if not self._drain_event:
            self._drain_event = asyncio.Event()

        await self._drain_event.wait()

    async def graceful_shutdown(self):
        self._allow_new_games = False
