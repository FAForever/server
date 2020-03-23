import pytest
from server.rating_service.rating_service import RatingService
from server.db import FAFDatabase

from server.rating import RatingType
from trueskill import Rating
from server.rating_service.typedefs import GameRatingSummary, RatingData
from server.games.game_results import GameOutcome


pytestmark = pytest.mark.asyncio


@pytest.fixture()
def service(database, player_service):
    return RatingService(database, player_service)


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


@pytest.mark.xfail
def test_get_new_player_rating(service):
    """
    What happens if a player doesn't have a rating table entry yet?
    """
    assert False
