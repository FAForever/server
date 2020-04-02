import pytest
from unittest import mock
from asynctest import CoroutineMock
import asyncio

from server.rating_service.rating_service import (
    RatingService,
    RatingNotFoundError,
    ServiceNotReadyError,
)
from server.db import FAFDatabase

from server.rating import RatingType
from trueskill import Rating
from server.rating_service.typedefs import GameRatingSummary, RatingData
from server.games.game_results import GameOutcome


pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def rating_service(database, player_service):
    service = RatingService(database, player_service)
    await service.initialize()
    yield service
    service.kill()


@pytest.fixture()
def uninitialized_service(database, player_service):
    return RatingService(database, player_service)


@pytest.fixture()
async def semiinitialized_service(database, player_service):
    service = RatingService(database, player_service)
    await service._load_rating_type_ids()
    return service


@pytest.fixture()
def game_rating_summary():
    summary_results = [{1: GameOutcome.VICTORY}, {2: GameOutcome.DEFEAT}]
    return GameRatingSummary(1, RatingType.GLOBAL, summary_results)


@pytest.fixture()
def bad_game_rating_summary():
    """
    Should throw a GameRatingError.
    """
    summary_results = [{1: GameOutcome.VICTORY}, {2: GameOutcome.VICTORY}]
    return GameRatingSummary(1, RatingType.GLOBAL, summary_results)


async def test_enqueue_manual_initialization(
    uninitialized_service, game_rating_summary
):
    service = uninitialized_service
    await service.initialize()
    service._rate = CoroutineMock()
    await service.enqueue(game_rating_summary)
    await service.shutdown()

    service._rate.assert_called()


async def test_enqueue_initialized_fixture(rating_service, game_rating_summary):
    service = rating_service
    service._rate = CoroutineMock()

    await service.enqueue(game_rating_summary)
    await service.shutdown()

    service._rate.assert_called()


async def test_enqueue_uninitialized(uninitialized_service):
    service = uninitialized_service
    with pytest.raises(ServiceNotReadyError):
        await service.enqueue(game_rating_summary)
    await service.shutdown()


async def test_load_rating_type_ids(uninitialized_service):
    service = uninitialized_service
    await service._load_rating_type_ids()

    assert service._rating_type_ids == {"global": 1, "ladder1v1": 2}


async def test_get_player_rating_global(semiinitialized_service):
    service = semiinitialized_service
    player_id = 50
    true_rating = Rating(1200, 250)
    rating = await service._get_player_rating(player_id, RatingType.GLOBAL)
    assert rating == true_rating


async def test_get_player_rating_ladder(semiinitialized_service):
    service = semiinitialized_service
    player_id = 50
    true_rating = Rating(1300, 400)
    rating = await service._get_player_rating(player_id, RatingType.LADDER_1V1)
    assert rating == true_rating


async def test_get_player_rating_legacy(semiinitialized_service):
    service = semiinitialized_service
    # Player 51 should have a rating entry in the old `global_rating`
    # and `ladder1v1_rating` tables but not in `leaderboard_rating`.
    player_id = 51
    legacy_global_rating = Rating(1201, 250)
    legacy_ladder_rating = Rating(1301, 400)

    rating = await service._get_player_rating(player_id, RatingType.GLOBAL)
    assert rating == legacy_global_rating

    rating = await service._get_player_rating(player_id, RatingType.LADDER_1V1)
    assert rating == legacy_ladder_rating


async def test_get_new_player_rating(semiinitialized_service):
    """
    What happens if a player doesn't have a rating table entry yet?
    """
    service = semiinitialized_service
    player_id = 999
    with pytest.raises(RatingNotFoundError):
        await service._get_player_rating(player_id, RatingType.LADDER_1V1)


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
        [{player1_id: player1_outcome}, {player2_id: player2_outcome}],
    )

    rating_data = await service._get_rating_data(summary)

    player1_expected_data = RatingData(player1_outcome, player1_db_rating)
    player2_expected_data = RatingData(player2_outcome, player2_db_rating)

    assert rating_data[0] == {player1_id: player1_expected_data}
    assert rating_data[1] == {player2_id: player2_expected_data}


async def test_rating(semiinitialized_service, game_rating_summary):
    service = semiinitialized_service
    service._persist_rating_changes = CoroutineMock()

    await service._rate(game_rating_summary)

    service._persist_rating_changes.assert_called()


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


async def test_game_rating_error_handled(
    rating_service, game_rating_summary, bad_game_rating_summary
):
    service = rating_service
    service._persist_rating_changes = CoroutineMock()
    service._logger = mock.Mock()

    await service.enqueue(bad_game_rating_summary)
    await service.enqueue(game_rating_summary)

    await service._join_rating_queue()

    # first game: error has been logged.
    service._logger.warning.assert_called()
    # second game: results have been saved.
    service._persist_rating_changes.assert_called_once()


async def test_nonexisting_rating_error_handled(rating_service, game_rating_summary):
    service = rating_service
    service._persist_rating_changes = CoroutineMock()
    service._logger = mock.Mock()

    bad_results = [{999: GameOutcome.VICTORY}, {888: GameOutcome.DEFEAT}]
    bad_summary = GameRatingSummary(1, RatingType.GLOBAL, bad_results)
    await service.enqueue(bad_summary)
    await service.enqueue(game_rating_summary)

    await service._join_rating_queue()

    # first game: error has been logged.
    service._logger.warning.assert_called()
    # second game: results have been saved.
    service._persist_rating_changes.assert_called_once()
