import pytest

from server.games.game_results import GameOutcome
from server.rating import RatingType
from server.rating_service.game_rater import GameRater
from server.rating_service.typedefs import TeamRatingData
from trueskill import Rating


class MockPlayer:
    ratings = {RatingType.GLOBAL: (1500, 500), RatingType.LADDER_1V1: (1500, 500)}


@pytest.fixture
def rating_data_1v1():
    player1_id = 1
    player1_rating = Rating(1500, 500)
    player1_outcome = GameOutcome.VICTORY

    player2_id = 2
    player2_rating = Rating(1400, 400)
    player2_outcome = GameOutcome.DEFEAT

    return [
        TeamRatingData(player1_outcome, {player1_id: player1_rating}),
        TeamRatingData(player2_outcome, {player2_id: player2_rating}),
    ]


@pytest.fixture
def rating_data_2v2():
    player1_id = 1
    player1_rating = Rating(1500, 500)

    player2_id = 2
    player2_rating = Rating(1400, 400)

    player3_id = 3
    player3_rating = Rating(1300, 300)

    player4_id = 4
    player4_rating = Rating(1200, 200)

    team1_outcome = GameOutcome.VICTORY
    team2_outcome = GameOutcome.DEFEAT

    return [
        TeamRatingData(
            team1_outcome, {player1_id: player1_rating, player2_id: player2_rating}
        ),
        TeamRatingData(
            team2_outcome, {player3_id: player3_rating, player4_id: player4_rating}
        ),
    ]


def test_compute_rating_1v1(rating_data_1v1):
    old_ratings = {
        player_id: rating
        for team in rating_data_1v1
        for player_id, rating in team.ratings.items()
    }

    new_ratings = GameRater.compute_rating(rating_data_1v1)

    assert new_ratings[1] > old_ratings[1]
    assert new_ratings[2] < old_ratings[2]

    assert new_ratings[1].sigma < old_ratings[1].sigma
    assert new_ratings[2].sigma < old_ratings[2].sigma


def test_compute_rating_2v2(rating_data_2v2):
    old_ratings = {
        player_id: rating
        for team in rating_data_2v2
        for player_id, rating in team.ratings.items()
    }

    new_ratings = GameRater.compute_rating(rating_data_2v2)

    assert new_ratings[1] > old_ratings[1]
    assert new_ratings[2] > old_ratings[2]
    assert new_ratings[3] < old_ratings[3]
    assert new_ratings[4] < old_ratings[4]

    assert new_ratings[1].sigma < old_ratings[1].sigma
    assert new_ratings[2].sigma < old_ratings[2].sigma
    assert new_ratings[3].sigma < old_ratings[3].sigma
    assert new_ratings[4].sigma < old_ratings[4].sigma
