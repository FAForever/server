from typing import Dict
from .typedefs import (
    TeamRatingData,
    GameRatingData,
    GameRatingSummary,
    PlayerID,
    ServiceNotReadyError,
    RatingNotFoundError,
    EntryNotFoundError,
)

import asyncio

from server.db import FAFDatabase
from server.core import Service
from server.player_service import PlayerService
from server.decorators import with_logger
from server.metrics import rating_service_backlog

from server.games.game_results import GameOutcome
from server.games.game import ValidityState

from server.rating import RatingType
from trueskill import Rating
from .game_rater import GameRater, GameRatingError

from sqlalchemy import select, and_
from server.db.models import legacy_ladder1v1_rating as legacy_ladder1v1_table
from server.db.models import legacy_global_rating as legacy_global_table
from server.db.models import leaderboard_rating as rating_table
from server.db.models import leaderboard as rating_type_table
from server.db.models import game_player_stats as gps_table


@with_logger
class RatingService(Service):
    """
    Service responsible for calculating and saving trueskill rating updates.
    To avoid race conditions, rating updates from a single game ought to be
    atomic.
    """

    def __init__(self, database: FAFDatabase, player_service: PlayerService):
        self._db = database
        self._player_service_callback = player_service.signal_player_rating_change
        self._accept_input = False
        self._queue = asyncio.Queue()
        self._task = None
        self._rating_type_ids = None

    async def initialize(self) -> None:
        if self._task is not None:
            self._logger.error("Service already runnning or not properly shut down.")
            return

        await self._load_rating_type_ids()
        self._accept_input = True
        self._logger.debug("RatingService starting...")
        self._task = asyncio.create_task(self._handle_rating_queue())

    async def _load_rating_type_ids(self):
        async with self._db.acquire() as conn:
            sql = select([rating_type_table.c.id, rating_type_table.c.technical_name])
            result = await conn.execute(sql)
            rows = await result.fetchall()

        self._rating_type_ids = {row["technical_name"]: row["id"] for row in rows}

    async def enqueue(self, summary: GameRatingSummary) -> None:
        if not self._accept_input:
            self._logger.warning("Dropped rating request %s", summary)
            raise ServiceNotReadyError(
                "RatingService not yet initialized or shutting down."
            )

        self._logger.debug("Queued up rating request %s", summary)
        await self._queue.put(summary)
        rating_service_backlog.set(self._queue.qsize())

    async def _handle_rating_queue(self) -> None:
        self._logger.info("RatingService started!")
        while self._accept_input or not self._queue.empty():
            summary = await self._queue.get()
            self._logger.debug("Now rating request %s", summary)

            try:
                await self._rate(summary)
            except GameRatingError:
                self._logger.warning("Error rating game %s", summary)
            except RatingNotFoundError:
                self._logger.warning("Missing rating entry to rate game %s", summary)
            except Exception:
                self._logger.exception("Failed rating request %s", summary)
            else:
                self._logger.debug("Done rating request.")

            self._queue.task_done()
            rating_service_backlog.set(self._queue.qsize())

        self._logger.info("RatingService stopped.")

    async def _rate(self, summary: GameRatingSummary) -> None:
        rating_data = await self._get_rating_data(summary)
        new_ratings = GameRater.compute_rating(rating_data)

        outcome_map = {
            player_id: team.outcome
            for team in summary.teams
            for player_id in team.player_ids
        }

        old_ratings = {
            player_id: rating
            for team in rating_data
            for player_id, rating in team.ratings.items()
        }
        await self._persist_rating_changes(
            summary.game_id, summary.rating_type, old_ratings, new_ratings, outcome_map
        )

    async def _get_rating_data(self, summary: GameRatingSummary) -> GameRatingData:
        ratings = {}
        for team in summary.teams:
            for player_id in team.player_ids:
                ratings[player_id] = await self._get_player_rating(
                    player_id, summary.rating_type
                )

        return [
            TeamRatingData(
                team.outcome,
                {player_id: ratings[player_id] for player_id in team.player_ids},
            )
            for team in summary.teams
        ]

    async def _get_player_rating(
        self, player_id: int, rating_type: RatingType
    ) -> Rating:
        if self._rating_type_ids is None:
            self._logger.warning(
                "Tried to fetch player data before initializing service."
            )
            raise ServiceNotReadyError("RatingService not yet initialized.")

        rating_type_id = self._rating_type_ids.get(rating_type.value)
        if rating_type_id is None:
            raise ValueError(f"Unknown rating type {rating_type}.")

        async with self._db.acquire() as conn:
            sql = select([rating_table.c.mean, rating_table.c.deviation]).where(
                and_(
                    rating_table.c.login_id == player_id,
                    rating_table.c.leaderboard_id == rating_type_id,
                )
            )

            result = await conn.execute(sql)
            row = await result.fetchone()

        if not row:
            return await self._get_player_legacy_rating(player_id, rating_type)

        return Rating(row[rating_table.c.mean], row[rating_table.c.deviation])

    async def _get_player_legacy_rating(
        self, player_id: int, rating_type: RatingType
    ) -> Rating:
        if rating_type is RatingType.GLOBAL:
            table = legacy_global_table
            sql = select([table.c.mean, table.c.deviation, table.c.numGames]).where(
                table.c.id == player_id
            )
        elif rating_type is RatingType.LADDER_1V1:
            table = legacy_ladder1v1_table
            sql = select(
                [table.c.mean, table.c.deviation, table.c.numGames, table.c.winGames]
            ).where(table.c.id == player_id)
        else:
            raise ValueError(f"Unknown rating type {rating_type}.")

        async with self._db.acquire() as conn:

            result = await conn.execute(sql)
            row = await result.fetchone()

            if not row:
                raise RatingNotFoundError(
                    f"Could not find a {rating_type} rating for player {player_id}."
                )

            if rating_type is RatingType.GLOBAL:
                # The old `global_rating` table does not have a `winGames` column.
                # This should be a decent approximation though.
                won_games = row[table.c.numGames] // 2
            else:
                won_games = row[table.c.winGames]

            await conn.execute(
                "INSERT INTO leaderboard_rating "
                "(login_id, mean, deviation, total_games, won_games, leaderboard_id) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                player_id,
                row[table.c.mean],
                row[table.c.deviation],
                row[table.c.numGames],
                won_games,
                self._rating_type_ids[rating_type.value],
            )

            return Rating(row[table.c.mean], row[table.c.deviation])

    async def _persist_rating_changes(
        self,
        game_id: int,
        rating_type: RatingType,
        old_ratings: Dict[PlayerID, Rating],
        new_ratings: Dict[PlayerID, Rating],
        outcomes: Dict[PlayerID, GameOutcome],
    ) -> None:
        """
        Persist computed ratings to the respective players' selected rating
        """
        self._logger.info("Saving rating change stats for game %i", game_id)

        async with self._db.acquire() as conn:
            for player_id, new_rating in new_ratings.items():
                old_rating = old_ratings[player_id]
                self._logger.debug(
                    "New %s rating for player with id %s: %s -> %s",
                    rating_type,
                    player_id,
                    old_rating,
                    new_rating,
                )
                await conn.execute(
                    "UPDATE game_player_stats "
                    "SET after_mean = %s, after_deviation = %s, "
                    "mean = %s, deviation = %s, scoreTime = NOW() "
                    "WHERE gameId = %s AND playerId = %s",
                    (
                        new_rating.mu,
                        new_rating.sigma,
                        old_rating.mu,
                        old_rating.sigma,
                        game_id,
                        player_id,
                    ),
                )

                gps_rows = await conn.execute(
                    select([gps_table.c.id]).where(
                        and_(
                            gps_table.c.playerId == player_id,
                            gps_table.c.gameId == game_id,
                        )
                    )
                )
                gps_row = await gps_rows.fetchone()
                if gps_row is None:
                    self._logger.warning(
                        f"No game_player_stats entry for player {player_id} of game {game_id}."
                    )
                    raise EntryNotFoundError
                game_player_stats_id = gps_row[gps_table.c.id]

                await self._update_rating_tables(
                    conn,
                    game_player_stats_id,
                    rating_type,
                    player_id,
                    new_rating,
                    old_rating,
                    outcomes[player_id],
                )

                self._update_player_object(player_id, rating_type, new_rating)

    async def _update_rating_tables(
        self,
        conn,
        game_player_stats_id: int,
        rating_type: RatingType,
        player_id: PlayerID,
        new_rating: Rating,
        old_rating: Rating,
        outcome: GameOutcome,
    ) -> None:

        is_victory = outcome is GameOutcome.VICTORY
        rating_type_id = self._rating_type_ids[rating_type.value]

        await conn.execute(
            "INSERT INTO leaderboard_rating_journal "
            "(game_player_stats_id, leaderboard_id, rating_mean_before, "
            "rating_deviation_before, rating_mean_after, rating_deviation_after) "
            "VALUES(%s, %s, %s, %s, %s, %s)",
            (
                game_player_stats_id,
                rating_type_id,
                old_rating.mu,
                old_rating.sigma,
                new_rating.mu,
                new_rating.sigma,
            ),
        )

        await conn.execute(
            "UPDATE leaderboard_rating "
            "SET mean = %s, deviation = %s, total_games = total_games + 1, "
            "won_games = won_games + %s "
            "WHERE login_id = %s AND leaderboard_id = %s",
            (
                new_rating.mu,
                new_rating.sigma,
                1 if is_victory else 0,
                player_id,
                rating_type_id,
            ),
        )

    def _update_player_object(
        self, player_id: PlayerID, rating_type: RatingType, new_rating: Rating
    ) -> None:
        if self._player_service_callback is None:
            self._logger.warning(
                "Tried to send rating change to player service, "
                "but no service was registered."
            )
            return

        self._logger.debug(
            "Sending player rating update for player with id %i", player_id
        )
        self._player_service_callback(player_id, rating_type, new_rating)

    async def _join_rating_queue(self) -> None:
        """
        Offers a call that is blocking until the rating queue has been emptied.
        Mostly for testing purposes.
        """
        await self._queue.join()

    async def shutdown(self) -> None:
        """
        Finish rating all remaining games, then exit.
        """
        self._accept_input = False
        self._logger.debug(
            "Shutdown initiated. Waiting on current queue: %s", self._queue
        )
        await self._queue.join()
        self._task = None
        self._logger.debug("Queue emptied: %s", self._queue)

    def kill(self) -> None:
        """
        Exit without waiting for the queue to join.
        """
        self._accept_input = False
        if self._task is not None:
            self._task.cancel()
            self._task = None