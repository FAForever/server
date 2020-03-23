import pytest
from unittest import mock
from asynctest import CoroutineMock

from server.rating_service.rating_service import RatingService, RatingNotFoundError
from server.db import FAFDatabase

from server.rating import RatingType
from trueskill import Rating
from server.rating_service.typedefs import GameRatingSummary, RatingData
from server.games.game_results import GameOutcome


pytestmark = pytest.mark.asyncio


@pytest.fixture()
def service(database, player_service):
    return RatingService(database, player_service)


@pytest.fixture()
def game_rating_summary():
    summary_results = [{1: GameOutcome.VICTORY}, {2: GameOutcome.DEFEAT}]
    return GameRatingSummary(1, RatingType.GLOBAL, summary_results)


async def test_get_player_rating_global(service):
    player_id = 50
    true_rating = Rating(1200, 250)
    rating = await service._get_player_rating(player_id, RatingType.GLOBAL)
    assert rating == true_rating


async def test_get_player_rating_ladder(service):
    player_id = 50
    true_rating = Rating(1300, 400)
    rating = await service._get_player_rating(player_id, RatingType.LADDER_1V1)
    assert rating == true_rating


async def test_get_new_player_rating(service):
    """
    What happens if a player doesn't have a rating table entry yet?
    """
    player_id = 999
    with pytest.raises(RatingNotFoundError):
        await service._get_player_rating(player_id, RatingType.LADDER_1V1)


async def test_get_rating_data(service):
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


async def test_rating(service, game_rating_summary):
    service._persist_rating_changes = CoroutineMock()

    await service.rate(game_rating_summary)

    service._persist_rating_changes.assert_called()


async def test_update_player_service(service, player_service):
    player_id = 1
    player_service._players = {player_id: mock.MagicMock()}

    service._update_player_object(player_id, RatingType.GLOBAL, Rating(1000, 100))

    player_service[player_id].ratings.__setitem__.assert_called()


async def test_update_player_service_failure_warning(service):
    service._player_service_callback = None
    service._logger = mock.MagicMock()

    service._update_player_object(1, RatingType.GLOBAL, Rating(1000, 100))

    service._logger.warn.assert_called()
