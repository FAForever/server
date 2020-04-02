from typing import Dict
from .typedefs import (
    RatingData,
    GameRatingData,
    GameRatingSummary,
    PlayerID,
    ServiceNotReadyError,
    RatingNotFoundError,
)

import asyncio

from server.db import FAFDatabase
from server.player_service import PlayerService
from server.decorators import with_logger
from server.metrics import rating_service_backlog

from server.games.game_results import GameOutcome
from server.games.game import ValidityState

from server.rating import RatingType
from trueskill import Rating
from .game_rater import GameRater, GameRatingError

from sqlalchemy import select
from server.db.models import ladder1v1_rating as ladder1v1_table
from server.db.models import global_rating as global_table


@with_logger
class RatingService:
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

    async def initialize(self) -> None:
        if self._task is not None:
            self._logger.error("Service already runnning or not properly shut down.")
            return
        self._accept_input = True
        self._logger.debug("RatingService starting...")
        self._task = asyncio.create_task(self._handle_rating_queue())

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
                await self._persist_rating_error(summary.game_id)
            except RatingNotFoundError:
                self._logger.warning("Missing rating entry to rate game %s", summary)
            else:
                self._logger.debug("Done rating request.")

            self._queue.task_done()
            rating_service_backlog.set(self._queue.qsize())

        self._logger.info("RatingService stopped.")

    async def _rate(self, summary: GameRatingSummary) -> None:
        rating_data = await self._get_rating_data(summary)
        new_ratings, final_outcomes = GameRater.compute_rating(rating_data)
        old_ratings = {
            player_id: data.rating
            for team in rating_data
            for player_id, data in team.items()
        }
        await self._persist_rating_changes(
            summary.game_id,
            summary.rating_type,
            old_ratings,
            new_ratings,
            final_outcomes,
        )

    async def _get_rating_data(self, summary: GameRatingSummary) -> GameRatingData:
        ratings = {}
        for player_id in (p for team in summary.results for p in team):
            ratings[player_id] = await self._get_player_rating(
                player_id, summary.rating_type
            )

        return [
            {
                player_id: RatingData(outcomes[player_id], ratings[player_id])
                for player_id in outcomes
            }
            for outcomes in summary.results
        ]

    async def _get_player_rating(
        self, player_id: int, rating_type: RatingType
    ) -> Rating:
        if rating_type is RatingType.GLOBAL:
            table = global_table
        elif rating_type is RatingType.LADDER_1V1:
            table = ladder1v1_table
        else:
            raise ValueError(f"Unknown rating type {rating_type}.")

        async with self._db.acquire() as conn:
            sql = select([table.c.mean, table.c.deviation]).where(
                table.c.id == player_id
            )

            result = await conn.execute(sql)
            row = await result.fetchone()

            if not row:
                raise RatingNotFoundError(
                    f"Could not find a {rating_type} rating for player {player_id}."
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
        # FIXME old_ratings only passed for logging, but might be nice with new
        # tables. If not used in new tables, throw it out.
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
                    "SET after_mean = %s, after_deviation = %s, scoreTime = NOW() "
                    "WHERE gameId = %s AND playerId = %s",
                    (new_rating.mu, new_rating.sigma, game_id, player_id),
                )

                await self._update_rating_table(
                    conn, rating_type, player_id, new_rating, outcomes[player_id]
                )

                self._update_player_object(player_id, rating_type, new_rating)

    async def _update_rating_table(
        self,
        conn,
        rating_type: RatingType,
        player_id: PlayerID,
        new_rating: Rating,
        outcome: GameOutcome,
    ) -> None:
        # If we are updating the ladder1v1_rating table then we also need to update
        # the `winGames` column which doesn't exist on the global_rating table
        table = f"{rating_type.value}_rating"

        if rating_type is RatingType.LADDER_1V1:
            is_victory = outcome is GameOutcome.VICTORY
            await conn.execute(
                "UPDATE ladder1v1_rating "
                "SET mean = %s, is_active=1, deviation = %s, numGames = numGames + 1, winGames = winGames + %s "
                "WHERE id = %s",
                (new_rating.mu, new_rating.sigma, 1 if is_victory else 0, player_id),
            )
        else:
            await conn.execute(
                "UPDATE " + table + " "
                "SET mean = %s, is_active=1, deviation = %s, numGames = numGames + 1 "
                "WHERE id = %s",
                (new_rating.mu, new_rating.sigma, player_id),
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
            "Sending player rating update for player with id ", player_id
        )
        self._player_service_callback(player_id, rating_type, new_rating)

    async def _persist_rating_error(self, game_id: int) -> None:
        validity_state = ValidityState.UNKNOWN_RESULT
        async with self._db.acquire() as conn:
            await conn.execute(
                "UPDATE game_stats SET validity = %s " "WHERE id = %s",
                (validity_state.value, game_id),
            )

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
