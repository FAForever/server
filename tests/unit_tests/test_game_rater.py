import pytest

from server.games.game_results import GameOutcome
from server.games.typedefs import TeamRatingSummary
from server.rating import Rating, RatingType
from server.rating_service.game_rater import GameRater


@pytest.fixture
def rating_data_1v1():
    player1_id = 1
    player2_id = 2

    ratings = {
        player1_id: Rating(1500, 500),
        player2_id: Rating(1400, 400),
    }

    return [
        TeamRatingSummary(GameOutcome.VICTORY, set((player1_id,)), []),
        TeamRatingSummary(GameOutcome.DEFEAT, set((player2_id,)), [])
    ], ratings


@pytest.fixture
def rating_data_2v2():
    player1_id = 1
    player2_id = 2
    player3_id = 3
    player4_id = 4

    ratings = {
        player1_id: Rating(1500, 500),
        player2_id: Rating(1400, 400),
        player3_id: Rating(1300, 300),
        player4_id: Rating(1200, 200)
    }

    return [
        TeamRatingSummary(GameOutcome.VICTORY, set((player1_id, player2_id)), []),
        TeamRatingSummary(GameOutcome.DEFEAT, set((player3_id, player4_id)), [])
    ], ratings


def test_compute_rating_1v1(rating_data_1v1):
    summary, old_ratings = rating_data_1v1
    new_ratings = GameRater.compute_rating(summary, old_ratings)

    assert new_ratings[1].mean > old_ratings[1].mean
    assert new_ratings[2].mean < old_ratings[2].mean

    assert new_ratings[1].dev < old_ratings[1].dev
    assert new_ratings[2].dev < old_ratings[2].dev


def test_compute_rating_2v2(rating_data_2v2):
    summary, old_ratings = rating_data_2v2
    new_ratings = GameRater.compute_rating(summary, old_ratings)

    assert new_ratings[1].mean > old_ratings[1].mean
    assert new_ratings[2].mean > old_ratings[2].mean
    assert new_ratings[3].mean < old_ratings[3].mean
    assert new_ratings[4].mean < old_ratings[4].mean

    assert new_ratings[1].dev < old_ratings[1].dev
    assert new_ratings[2].dev < old_ratings[2].dev
    assert new_ratings[3].dev < old_ratings[3].dev
    assert new_ratings[4].dev < old_ratings[4].dev
