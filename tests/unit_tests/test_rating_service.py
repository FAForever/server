from unittest import mock

import pytest
from sqlalchemy import and_, select

from server.db import FAFDatabase
from server.db.models import (
    game_player_stats,
    leaderboard_rating,
    leaderboard_rating_journal
)
from server.games.game_results import ArmyResult, GameOutcome
from server.games.typedefs import (
    EndedGameInfo,
    TeamRatingSummary,
    ValidityState
)
from server.rating import Leaderboard, Rating, RatingType
from server.rating_service.game_rater import GameRater
from server.rating_service.rating_service import (
    RatingService,
    ServiceNotReadyError
)
from server.rating_service.typedefs import GameRatingSummary


@pytest.fixture
async def rating_service(database, player_service, message_queue_service):
    service = RatingService(database, player_service, message_queue_service)
    await service.initialize()
    yield service
    service.kill()


@pytest.fixture
def uninitialized_service(database, player_service, message_queue_service):
    return RatingService(database, player_service, message_queue_service)


@pytest.fixture
async def semiinitialized_service(
    database,
    player_service,
    message_queue_service
):
    service = RatingService(database, player_service, message_queue_service)
    await service.update_data()
    return service


@pytest.fixture
def game_rating_summary():
    return GameRatingSummary(
        1,
        RatingType.GLOBAL,
        [
            TeamRatingSummary(
                GameOutcome.VICTORY, {1}, [ArmyResult(1, 0, "VICTORY", [])]
            ),
            TeamRatingSummary(
                GameOutcome.DEFEAT, {2}, [ArmyResult(2, 1, "DEFEAT", [])],
            ),
        ],
    )


@pytest.fixture
def game_info():
    return EndedGameInfo(
        1,
        RatingType.GLOBAL,
        1,
        "faf",
        [],
        {},
        ValidityState.VALID,
        [
            TeamRatingSummary(
                GameOutcome.VICTORY, {1}, [ArmyResult(1, 0, "VICTORY", [])]
            ),
            TeamRatingSummary(
                GameOutcome.DEFEAT, {2}, [ArmyResult(2, 1, "DEFEAT", [])],
            ),
        ],
    )


@pytest.fixture
def bad_game_info():
    """
    Should throw a GameRatingError.
    """
    return EndedGameInfo(
        1,
        RatingType.GLOBAL,
        1,
        "faf",
        [],
        {},
        ValidityState.VALID,
        [
            TeamRatingSummary(
                GameOutcome.VICTORY, {1}, [ArmyResult(1, 0, "VICTORY", [])]
            ),
            TeamRatingSummary(
                GameOutcome.VICTORY, {2}, [ArmyResult(2, 1, "VICTORY", [])],
            ),
        ],
    )


async def test_enqueue_manual_initialization(uninitialized_service, game_info):
    service = uninitialized_service
    await service.initialize()
    service._rate = mock.AsyncMock()
    await service.enqueue(game_info.to_dict())
    await service.shutdown()

    service._rate.assert_called()


async def double_initialization_does_not_start_second_worker(rating_service):
    worker_task_id = id(rating_service._task)

    await rating_service.initialize()

    assert worker_task_id == id(rating_service._task)


async def test_enqueue_initialized(rating_service, game_info):
    service = rating_service
    service._rate = mock.AsyncMock()

    await service.enqueue(game_info.to_dict())
    await service.shutdown()

    service._rate.assert_called()


async def test_enqueue_uninitialized(uninitialized_service, game_info):
    service = uninitialized_service
    with pytest.raises(ServiceNotReadyError):
        await service.enqueue(game_info.to_dict())
    await service.shutdown()


async def test_load_from_database(uninitialized_service):
    service = uninitialized_service
    assert service._rating_type_ids is None
    assert service.leaderboards == {}

    await service.update_data()

    assert service._rating_type_ids == {
        "global": 1,
        "ladder_1v1": 2,
        "tmm_2v2": 3
    }
    global_ = Leaderboard(1, "global")
    assert service.leaderboards == {
        "global": global_,
        "ladder_1v1": Leaderboard(2, "ladder_1v1"),
        "tmm_2v2": Leaderboard(3, "tmm_2v2", global_)
    }


async def get_all_ratings(db: FAFDatabase, player_id: int):
    rating_sql = select([leaderboard_rating]).where(
        and_(leaderboard_rating.c.login_id == player_id)
    )

    async with db.acquire() as conn:
        result = await conn.execute(rating_sql)
        rows = result.fetchall()

    return rows


async def test_new_player_rating_created(semiinitialized_service):
    """
    Upon rating games of players without a rating entry, a new rating entry
    should be created.
    """
    service = semiinitialized_service
    player_id = 300
    rating_type = RatingType.LADDER_1V1
    summary = GameRatingSummary(
        1,
        RatingType.GLOBAL,
        [
            TeamRatingSummary(
                GameOutcome.VICTORY,
                {player_id},
                [ArmyResult(player_id, 0, "VICTORY", [])]
            ),
            TeamRatingSummary(
                GameOutcome.DEFEAT,
                {2},
                [ArmyResult(2, 1, "DEFEAT", [])],
            ),
        ],
    )

    db_ratings = await get_all_ratings(service._db, player_id)
    assert len(db_ratings) == 0  # Rating does not exist yet

    async with service._db.acquire() as conn:
        player_ratings = await service._get_all_player_ratings(
            conn, [player_id, 2]
        )
        await service._rate_for_leaderboard(
            conn,
            summary.game_id,
            rating_type,
            player_ratings,
            GameRater(summary)
        )

    db_ratings = await get_all_ratings(service._db, player_id)
    assert len(db_ratings) == 1  # Rating has been created
    assert db_ratings[0]["mean"] == 1500
    assert db_ratings[0]["deviation"] == 500


async def test_rating(semiinitialized_service, game_rating_summary):
    service = semiinitialized_service
    service._persist_rating_changes = mock.AsyncMock()

    await service._rate(game_rating_summary)

    service._persist_rating_changes.assert_called()


async def test_rating_persistence(semiinitialized_service):
    # Assumes that game_player_stats has an entry for player 1 in game 1.
    service = semiinitialized_service
    game_id = 1
    player_id = 1
    rating_type = RatingType.GLOBAL
    rating_type_id = service._rating_type_ids[RatingType.GLOBAL]
    old_ratings = {player_id: Rating(1000, 500)}
    after_mean = 1234
    new_ratings = {player_id: Rating(after_mean, 400)}
    outcomes = {player_id: GameOutcome.VICTORY}

    async with service._db.acquire() as conn:
        await service._persist_rating_changes(
            conn, game_id, rating_type, old_ratings, new_ratings, outcomes
        )

        sql = select([game_player_stats.c.id, game_player_stats.c.after_mean]).where(
            and_(
                game_player_stats.c.gameId == game_id,
                game_player_stats.c.playerId == player_id,
            )
        )
        result = await conn.execute(sql)
        gps_row = result.fetchone()

        sql = select([leaderboard_rating.c.mean]).where(
            and_(
                leaderboard_rating.c.login_id == player_id,
                leaderboard_rating.c.leaderboard_id == rating_type_id,
            )
        )
        result = await conn.execute(sql)
        rating_row = result.fetchone()

        sql = select([leaderboard_rating_journal.c.rating_mean_after]).where(
            leaderboard_rating_journal.c.game_player_stats_id
            == gps_row[game_player_stats.c.id]
        )
        result = await conn.execute(sql)
        journal_row = result.fetchone()

    assert gps_row[game_player_stats.c.after_mean] == after_mean
    assert rating_row[leaderboard_rating.c.mean] == after_mean
    assert journal_row[leaderboard_rating_journal.c.rating_mean_after] == after_mean


async def test_update_player_service(uninitialized_service, player_service):
    service = uninitialized_service
    player_id = 1
    player_service._players = {player_id: mock.MagicMock()}

    service._update_player_object(player_id, RatingType.GLOBAL, Rating(1000, 100))

    player_service[player_id].ratings.__setitem__.assert_called()


async def test_update_player_service_failure_warning(uninitialized_service):
    service = uninitialized_service
    service._player_service_callback = None
    service._logger = mock.Mock()

    service._update_player_object(1, RatingType.GLOBAL, Rating(1000, 100))

    service._logger.warning.assert_called()


async def test_game_rating_error_handled(rating_service, game_info, bad_game_info):
    service = rating_service
    service._persist_rating_changes = mock.AsyncMock()
    service._logger = mock.Mock()

    await service.enqueue(bad_game_info.to_dict())
    await service.enqueue(game_info.to_dict())

    await service._join_rating_queue()

    # first game: error has been logged.
    service._logger.warning.assert_called()
    # second game: results have been saved.
    service._persist_rating_changes.assert_called_once()


async def test_game_update_empty_resultset(rating_service):
    service = rating_service
    game_id = 2
    player_id = 1
    rating_type = RatingType.GLOBAL
    old_ratings = {player_id: Rating(1000, 500)}
    after_mean = 1234
    new_ratings = {player_id: Rating(after_mean, 400)}
    outcomes = {player_id: GameOutcome.VICTORY}

    async with service._db.acquire() as conn:
        await service._persist_rating_changes(
            conn, game_id, rating_type, old_ratings, new_ratings, outcomes
        )
