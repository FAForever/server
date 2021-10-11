from unittest import mock

import pytest
from asynctest import CoroutineMock
from sqlalchemy import and_, select
from trueskill import Rating

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
from server.rating import Leaderboard, RatingType
from server.rating_service.rating_service import (
    RatingService,
    ServiceNotReadyError
)
from server.rating_service.typedefs import GameRatingSummary, TeamRatingData

pytestmark = pytest.mark.asyncio


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
    service._rate = CoroutineMock()
    await service.enqueue(game_info.to_dict())
    await service.shutdown()

    service._rate.assert_called()


async def double_initialization_does_not_start_second_worker(rating_service):
    worker_task_id = id(rating_service._task)

    await rating_service.initialize()

    assert worker_task_id == id(rating_service._task)


async def test_enqueue_initialized(rating_service, game_info):
    service = rating_service
    service._rate = CoroutineMock()

    await service.enqueue(game_info.to_dict())
    await service.shutdown()

    service._rate.assert_called()


async def test_enqueue_uninitialized(uninitialized_service, game_info):
    service = uninitialized_service
    with pytest.raises(ServiceNotReadyError):
        await service.enqueue(game_info.to_dict())
    await service.shutdown()


async def test_get_rating_uninitialized(uninitialized_service):
    service = uninitialized_service
    with pytest.raises(ServiceNotReadyError):
        await service._get_players_ratings([1], RatingType.GLOBAL)


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


async def test_get_players_ratings_global(semiinitialized_service):
    service = semiinitialized_service
    player_id = 50
    true_rating = Rating(1200, 250)
    ratings = await service._get_players_ratings([player_id], RatingType.GLOBAL)
    assert ratings[player_id] == true_rating


async def test_get_players_ratings_ladder(semiinitialized_service):
    service = semiinitialized_service
    player_id = 50
    true_rating = Rating(1300, 400)
    ratings = await service._get_players_ratings([player_id], RatingType.LADDER_1V1)
    assert ratings[player_id] == true_rating


async def get_all_ratings(db: FAFDatabase, player_id: int):
    rating_sql = select([leaderboard_rating]).where(
        and_(leaderboard_rating.c.login_id == player_id)
    )

    async with db.acquire() as conn:
        result = await conn.execute(rating_sql)
        rows = await result.fetchall()

    return rows


async def test_get_new_player_rating_created(semiinitialized_service):
    """
    Upon rating games of players without a rating entry in both new and legacy
    tables, a new rating entry should be created.
    """
    service = semiinitialized_service
    player_id = 300
    rating_type = RatingType.LADDER_1V1

    db_ratings = await get_all_ratings(service._db, player_id)
    assert len(db_ratings) == 0  # Rating does not exist yet

    await service._get_players_ratings([player_id], rating_type)

    db_ratings = await get_all_ratings(service._db, player_id)
    assert len(db_ratings) == 1  # Rating has been created
    assert db_ratings[0]["mean"] == 1500
    assert db_ratings[0]["deviation"] == 500


async def test_get_rating_data(semiinitialized_service):
    service = semiinitialized_service
    game_id = 1

    player1_id = 1
    player1_db_rating = Rating(2000, 125)
    player1_outcome = GameOutcome.VICTORY

    player2_id = 2
    player2_db_rating = Rating(1500, 75)
    player2_outcome = GameOutcome.DEFEAT

    summary = GameRatingSummary(
        game_id,
        RatingType.GLOBAL,
        [
            TeamRatingSummary(
                player1_outcome, {1}, [
                    ArmyResult(player1_id, 0, player1_outcome.name, [])
                ],
            ),
            TeamRatingSummary(
                player2_outcome, {2}, [
                    ArmyResult(player2_id, 1, player2_outcome.name, [])
                ],
            ),
        ],
    )

    rating_data = await service._get_rating_data(summary)

    player1_expected_data = TeamRatingData(
        player1_outcome, {player1_id: player1_db_rating}
    )
    player2_expected_data = TeamRatingData(
        player2_outcome, {player2_id: player2_db_rating}
    )

    assert rating_data[0] == player1_expected_data
    assert rating_data[1] == player2_expected_data


async def test_rating(semiinitialized_service, game_rating_summary):
    service = semiinitialized_service
    service._persist_rating_changes = CoroutineMock()

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

    await service._persist_rating_changes(
        game_id, rating_type, old_ratings, new_ratings, outcomes
    )

    async with service._db.acquire() as conn:
        sql = select([game_player_stats.c.id, game_player_stats.c.after_mean]).where(
            and_(
                game_player_stats.c.gameId == game_id,
                game_player_stats.c.playerId == player_id,
            )
        )
        results = await conn.execute(sql)
        gps_row = await results.fetchone()

        sql = select([leaderboard_rating.c.mean]).where(
            and_(
                leaderboard_rating.c.login_id == player_id,
                leaderboard_rating.c.leaderboard_id == rating_type_id,
            )
        )
        results = await conn.execute(sql)
        rating_row = await results.fetchone()

        sql = select([leaderboard_rating_journal.c.rating_mean_after]).where(
            leaderboard_rating_journal.c.game_player_stats_id
            == gps_row[game_player_stats.c.id]
        )
        results = await conn.execute(sql)
        journal_row = await results.fetchone()

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
    service._persist_rating_changes = CoroutineMock()
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

    await service._persist_rating_changes(
        game_id, rating_type, old_ratings, new_ratings, outcomes
    )
