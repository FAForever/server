import asyncio
from typing import Dict, List, Optional

import aiocron
import pymysql
from sqlalchemy import and_, bindparam, func, select

from server.config import config
from server.core import Service
from server.db import FAFDatabase
from server.db.models import (
    game_player_stats,
    leaderboard,
    leaderboard_rating,
    leaderboard_rating_journal
)
from server.decorators import with_logger
from server.games.game_results import GameOutcome
from server.message_queue_service import MessageQueueService
from server.metrics import rating_service_backlog
from server.player_service import PlayerService
from server.rating import Leaderboard, PlayerRatings, Rating, RatingType

from .game_rater import AdjustmentGameRater, GameRater, GameRatingError
from .typedefs import (
    GameRatingResult,
    GameRatingSummary,
    PlayerID,
    RatingDict,
    ServiceNotReadyError
)


@with_logger
class RatingService(Service):
    """
    Service responsible for calculating and saving trueskill rating updates.
    To avoid race conditions, rating updates from a single game ought to be
    atomic.
    """

    def __init__(
        self,
        database: FAFDatabase,
        player_service: PlayerService,
        message_queue_service: MessageQueueService
    ):
        self._db = database
        self._player_service_callback = player_service.signal_player_rating_change
        self._accept_input = False
        self._queue = asyncio.Queue()
        self._task = None
        self._rating_type_ids: Optional[Dict[str, int]] = None
        self.leaderboards: Dict[str, Leaderboard] = {}
        self._message_queue_service = message_queue_service

    async def initialize(self) -> None:
        if self._task is not None:
            self._logger.error("Service already runnning or not properly shut down.")
            return

        await self.update_data()
        self._update_cron = aiocron.crontab("*/10 * * * *", func=self.update_data)
        self._accept_input = True
        self._logger.debug("RatingService starting...")
        self._task = asyncio.create_task(self._handle_rating_queue())

    async def update_data(self):
        async with self._db.acquire() as conn:
            initializer = leaderboard.alias()
            sql = select([
                leaderboard.c.id,
                leaderboard.c.technical_name,
                initializer.c.technical_name.label("initializer")
            ]).select_from(
                leaderboard.outerjoin(
                    initializer,
                    leaderboard.c.initializer_id == initializer.c.id
                )
            )
            result = await conn.execute(sql)
            rows = result.fetchall()

            self.leaderboards.clear()
            self._rating_type_ids = {}
            for row in rows:
                self.leaderboards[row.technical_name] = Leaderboard(
                    row.id,
                    row.technical_name
                )
                self._rating_type_ids[row.technical_name] = row.id

            # Link the initializers
            for row in rows:
                current = self.leaderboards[row.technical_name]
                init = self.leaderboards.get(row.initializer)
                if init:
                    current.initializer = init

    async def enqueue(self, game_info: Dict) -> None:
        if not self._accept_input:
            self._logger.warning("Dropped rating request %s", game_info)
            raise ServiceNotReadyError(
                "RatingService not yet initialized or shutting down."
            )

        summary = GameRatingSummary.from_game_info_dict(game_info)
        self._logger.debug("Queued up rating request %s", summary)
        await self._queue.put(summary)
        rating_service_backlog.set(self._queue.qsize())

    async def _handle_rating_queue(self) -> None:
        self._logger.debug("RatingService started!")
        try:
            while self._accept_input or not self._queue.empty():
                summary = await self._queue.get()
                self._logger.debug("Now rating request %s", summary)

                try:
                    await self._rate(summary)
                except GameRatingError:
                    self._logger.warning("Error rating game %s", summary)
                except Exception:  # pragma: no cover
                    self._logger.exception("Failed rating request %s", summary)
                else:
                    self._logger.debug("Done rating request.")

                self._queue.task_done()
                rating_service_backlog.set(self._queue.qsize())
        except asyncio.CancelledError:
            pass
        except Exception:  # pragma: no cover
            self._logger.critical(
                "Unexpected exception while handling rating queue.",
                exc_info=True
            )

        self._logger.debug("RatingService stopped.")

    async def _rate(self, summary: GameRatingSummary) -> None:
        assert self._rating_type_ids is not None

        if summary.rating_type not in self._rating_type_ids:
            raise GameRatingError(f"Unknown rating type {summary.rating_type}.")

        rater = GameRater(summary)
        rating_results = []

        async with self._db.acquire() as conn:
            # Fetch all players rating info from the database
            player_ratings = await self._get_all_player_ratings(
                conn, rater.player_ids
            )
            rating_result = await self._rate_for_leaderboard(
                conn,
                summary.game_id,
                summary.rating_type,
                player_ratings,
                rater
            )
            assert rating_result is not None
            rating_results.append(rating_result)

            # TODO: If we add hidden ratings, make sure to check for them here.
            # Hidden ratings should not affect global.
            # TODO: Use game_type == "matchmaker" instead?
            if summary.rating_type != RatingType.GLOBAL:
                self._logger.debug(
                    "Performing global rating adjustment for players: %s",
                    rater.player_ids
                )
                adjustment_rater = AdjustmentGameRater(
                    rater,
                    rating_result.old_ratings
                )
                global_rating_result = await self._rate_for_leaderboard(
                    conn,
                    summary.game_id,
                    RatingType.GLOBAL,
                    player_ratings,
                    adjustment_rater,
                    update_game_player_stats=False
                )
                if global_rating_result:
                    rating_results.append(global_rating_result)

        for rating_result in rating_results:
            await self._publish_rating_changes(
                rating_result.rating_type,
                rating_result.old_ratings,
                rating_result.new_ratings,
                rating_result.outcome_map
            )

    async def _rate_for_leaderboard(
        self,
        conn,
        game_id: int,
        rating_type: str,
        player_ratings: Dict[PlayerID, PlayerRatings],
        rater: GameRater,
        update_game_player_stats: bool = True
    ) -> Optional[GameRatingResult]:
        """
        Rates a game using a particular rating_type and GameRater.
        """
        uninitialized_ratings = {
            # Querying the key will create the value using rating
            # initialization, sort of like a defaultdict.
            player_id: Rating(*player_ratings[player_id][rating_type])
            for player_id in player_ratings.keys()
            if rating_type not in player_ratings[player_id]
        }
        # Initialize the ratings we need
        old_ratings = {
            player_id: Rating(*player_ratings[player_id][rating_type])
            for player_id in player_ratings.keys()
        }

        new_ratings = rater.compute_rating(old_ratings)
        if not new_ratings:
            return None

        need_initial_ratings = {
            player_id: rating
            for player_id, rating in uninitialized_ratings.items()
            if player_id in new_ratings
        }
        if need_initial_ratings:
            # Ensure that leaderboard entries exist before calling persist.
            await self._create_initial_ratings(
                conn,
                rating_type,
                need_initial_ratings
            )

        outcome_map = rater.get_outcome_map()
        # Now persist the changes for all players that get the adjustment.
        await self._persist_rating_changes(
            conn,
            game_id,
            rating_type,
            old_ratings,
            new_ratings,
            outcome_map,
            update_game_player_stats=update_game_player_stats
        )

        return GameRatingResult(
            rating_type,
            old_ratings,
            new_ratings,
            outcome_map
        )

    async def _create_initial_ratings(
        self,
        conn,
        rating_type: str,
        ratings: RatingDict
    ):
        assert self._rating_type_ids is not None

        leaderboard_id = self._rating_type_ids[rating_type]

        values = [
            dict(
                login_id=player_id,
                mean=rating.mean,
                deviation=rating.dev,
                total_games=0,
                won_games=0,
                leaderboard_id=leaderboard_id,
            )
            for player_id, rating in ratings.items()
        ]
        if values:
            await conn.execute(
                leaderboard_rating.insert(),
                values
            )

    async def _get_all_player_ratings(
        self, conn, player_ids: List[PlayerID]
    ) -> Dict[PlayerID, PlayerRatings]:
        sql = select([
            leaderboard_rating.c.login_id,
            leaderboard.c.technical_name,
            leaderboard_rating.c.mean,
            leaderboard_rating.c.deviation
        ]).join(leaderboard).where(
            leaderboard_rating.c.login_id.in_(player_ids)
        )
        result = await conn.execute(sql)

        player_ratings = {
            player_id: PlayerRatings(self.leaderboards, init=False)
            for player_id in player_ids
        }

        for row in result:
            player_id, rating_type = row.login_id, row.technical_name
            player_ratings[player_id][rating_type] = (row.mean, row.deviation)

        return player_ratings

    async def _persist_rating_changes(
        self,
        conn,
        game_id: int,
        rating_type: str,
        old_ratings: RatingDict,
        new_ratings: RatingDict,
        outcomes: Dict[PlayerID, GameOutcome],
        update_game_player_stats: bool = True
    ) -> None:
        """
        Persist computed ratings to the respective players' selected rating
        """
        assert self._rating_type_ids is not None

        self._logger.debug("Saving rating change stats for game %i", game_id)

        ratings = [
            (player_id, old_ratings[player_id], new_ratings[player_id])
            for player_id in new_ratings.keys()
        ]

        for player_id, new_rating, old_rating in ratings:
            self._logger.debug(
                "New %s rating for player with id %s: %s -> %s",
                rating_type,
                player_id,
                old_rating,
                new_rating,
            )

        if update_game_player_stats:
            # DEPRECATED: game_player_stats table contains rating data.
            # Use leaderboard_rating_journal instead
            gps_update_sql = (
                game_player_stats.update()
                .where(
                    and_(
                        game_player_stats.c.playerId == bindparam("player_id"),
                        game_player_stats.c.gameId == game_id,
                    )
                )
                .values(
                    after_mean=bindparam("after_mean"),
                    after_deviation=bindparam("after_deviation"),
                    mean=bindparam("mean"),
                    deviation=bindparam("deviation"),
                    scoreTime=func.now()
                )
            )
            try:
                result = await conn.execute(gps_update_sql, [
                    dict(
                        player_id=player_id,
                        after_mean=new_rating.mean,
                        after_deviation=new_rating.dev,
                        mean=old_rating.mean,
                        deviation=old_rating.dev,
                    )
                    for player_id, old_rating, new_rating in ratings
                ])

                if result.rowcount != len(ratings):
                    self._logger.warning(
                        "gps_update_sql only updated %d out of %d rows for game_id %d",
                        result.rowcount,
                        len(ratings),
                        game_id
                    )
                    return
            except pymysql.OperationalError:
                # Could happen if we drop the rating columns from game_player_stats
                self._logger.warning(
                    "gps_update_sql failed for game %d, ignoring...",
                    game_id,
                    exc_info=True
                )

        leaderboard_id = self._rating_type_ids[rating_type]

        journal_insert_sql = leaderboard_rating_journal.insert().values(
            leaderboard_id=leaderboard_id,
            rating_mean_before=bindparam("rating_mean_before"),
            rating_deviation_before=bindparam("rating_deviation_before"),
            rating_mean_after=bindparam("rating_mean_after"),
            rating_deviation_after=bindparam("rating_deviation_after"),
            game_player_stats_id=select([game_player_stats.c.id]).where(
                and_(
                    game_player_stats.c.playerId == bindparam("player_id"),
                    game_player_stats.c.gameId == game_id,
                )
            ).scalar_subquery(),
        )
        await conn.execute(journal_insert_sql, [
            dict(
                player_id=player_id,
                rating_mean_before=old_rating.mean,
                rating_deviation_before=old_rating.dev,
                rating_mean_after=new_rating.mean,
                rating_deviation_after=new_rating.dev,
            )
            for player_id, old_rating, new_rating in ratings
        ])

        rating_update_sql = (
            leaderboard_rating.update()
            .where(
                and_(
                    leaderboard_rating.c.login_id == bindparam("player_id"),
                    leaderboard_rating.c.leaderboard_id == leaderboard_id,
                )
            )
            .values(
                mean=bindparam("mean"),
                deviation=bindparam("deviation"),
                total_games=leaderboard_rating.c.total_games + 1,
                won_games=leaderboard_rating.c.won_games + bindparam("increment"),
            )
        )
        await conn.execute(rating_update_sql, [
            dict(
                player_id=player_id,
                mean=new_rating.mean,
                deviation=new_rating.dev,
                increment=(
                    1 if outcomes[player_id] is GameOutcome.VICTORY else 0
                )
            )
            for player_id, _, new_rating in ratings
        ])

        for player_id, new_rating in new_ratings.items():
            self._update_player_object(player_id, rating_type, new_rating)

    def _update_player_object(
        self, player_id: PlayerID, rating_type: str, new_rating: Rating
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

    async def _publish_rating_changes(
        self,
        rating_type: str,
        old_ratings: RatingDict,
        new_ratings: RatingDict,
        outcomes: Dict[PlayerID, GameOutcome],
    ):
        for player_id, new_rating in new_ratings.items():
            if player_id not in outcomes:
                self._logger.error("Missing outcome for player %i", player_id)
                continue
            if player_id not in old_ratings:
                self._logger.error("Missing old rating for player %i", player_id)
                continue

            old_rating = old_ratings[player_id]

            rating_change_dict = {
                "player_id": player_id,
                "rating_type": rating_type,
                "new_rating_mean": new_rating.mean,
                "new_rating_deviation": new_rating.dev,
                "old_rating_mean": old_rating.mean,
                "old_rating_deviation": old_rating.dev,
                "outcome": outcomes[player_id].value
            }

            await self._message_queue_service.publish(
                config.MQ_EXCHANGE_NAME,
                "success.rating.update",
                rating_change_dict,
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
        if self._queue.empty() and self._task:
            self._task.cancel()
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
