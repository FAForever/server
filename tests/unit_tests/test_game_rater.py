import pytest

from server.rating_service.game_rater import GameRater, GameRatingError
from server.rating_service.typedefs import GameRatingData, RatingData
from server.games.game_results import GameOutcome
from server.rating import RatingType
from trueskill import Rating


class MockPlayer:
    ratings = {RatingType.GLOBAL: (1500, 500), RatingType.LADDER_1V1: (1500, 500)}


@pytest.fixture
def rating_data_1v1():
    game_id = 111

    player1_id = 1
    player1_rating = Rating(1500, 500)
    player1_outcome = GameOutcome.VICTORY

    player2_id = 2
    player2_rating = Rating(1400, 400)
    player2_outcome = GameOutcome.DEFEAT

    return [
        {player1_id: RatingData(player1_outcome, player1_rating)},
        {player2_id: RatingData(player2_outcome, player2_rating)},
    ]


@pytest.fixture
def rating_data_2v2():
    game_id = 111

    player1_id = 1
    player1_rating = Rating(1500, 500)
    player1_outcome = GameOutcome.VICTORY

    player2_id = 2
    player2_rating = Rating(1400, 400)
    player2_outcome = GameOutcome.DEFEAT

    player3_id = 3
    player3_rating = Rating(1300, 300)
    player3_outcome = GameOutcome.DEFEAT

    player4_id = 4
    player4_rating = Rating(1200, 200)
    player4_outcome = GameOutcome.DEFEAT

    return [
        {
            player1_id: RatingData(player1_outcome, player1_rating),
            player2_id: RatingData(player2_outcome, player2_rating),
        },
        {
            player3_id: RatingData(player3_outcome, player3_rating),
            player4_id: RatingData(player4_outcome, player4_rating),
        },
    ]


def test_only_rate_with_two_parties():
    one_party = [{1: GameOutcome.VICTORY}]
    two_parties = [{1: GameOutcome.VICTORY}, {2: GameOutcome.DEFEAT}]
    three_parties = [
        {1: GameOutcome.VICTORY},
        {2: GameOutcome.DEFEAT},
        {3: GameOutcome.DEFEAT},
    ]

    with pytest.raises(GameRatingError):
        GameRater._check_rating_groups(one_party)

    with pytest.raises(GameRatingError):
        GameRater._check_rating_groups(three_parties)

    GameRater._check_rating_groups(two_parties)


def test_ranks_from_team_outcomes():
    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.DEFEAT}]

    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)

    assert ranks == [0, 1]  # first team won


def test_ranks_all_1v1_possibilities():
    """
    Document expectations for all outcomes of 1v1 games.
    Assumes that the order of teams doesn't matter.
    With six possible outcomes there are 21 possibilities.
    """
    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.VICTORY}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.DEFEAT}]
    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 1]  # first team won

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.DRAW}]
    GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 1]  # first team won

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.MUTUAL_DRAW}]
    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 1]  # first team won

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.UNKNOWN}]
    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 1]  # first team won

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.CONFLICTING}]
    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 1]  # first team won

    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.DEFEAT}]
    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 0]  # draw

    # TODO: is this actually intended behaviour?
    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.DRAW}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.MUTUAL_DRAW}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.UNKNOWN}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.DRAW}, {GameOutcome.DRAW}]
    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 0]  # draw

    team_outcomes = [{GameOutcome.DRAW}, {GameOutcome.MUTUAL_DRAW}]
    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 0]  # draw

    team_outcomes = [{GameOutcome.DRAW}, {GameOutcome.UNKNOWN}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.DRAW}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.MUTUAL_DRAW}, {GameOutcome.MUTUAL_DRAW}]
    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 0]  # draw

    team_outcomes = [{GameOutcome.MUTUAL_DRAW}, {GameOutcome.UNKNOWN}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.MUTUAL_DRAW}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.UNKNOWN}, {GameOutcome.UNKNOWN}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.UNKNOWN}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)

    team_outcomes = [{GameOutcome.CONFLICTING}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)


def test_team_outcome_ignores_unknown():
    team_outcomes = [
        {GameOutcome.VICTORY, GameOutcome.UNKNOWN},
        {GameOutcome.DEFEAT, GameOutcome.UNKNOWN},
    ]

    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)
    assert ranks == [0, 1]  # first team won


def test_team_outcome_throws_if_unilateral_draw():
    team_outcomes = [
        {GameOutcome.DRAW, GameOutcome.DEFEAT},
        {GameOutcome.DEFEAT, GameOutcome.UNKNOWN},
    ]

    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)


def test_team_outcome_throws_if_unilateral_mutual_draw():
    team_outcomes = [
        {GameOutcome.MUTUAL_DRAW, GameOutcome.DEFEAT},
        {GameOutcome.DEFEAT, GameOutcome.UNKNOWN},
    ]

    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)


def test_team_outcome_victory_has_priority_over_defeat():
    team_outcomes = [
        {GameOutcome.VICTORY, GameOutcome.DEFEAT},
        {GameOutcome.DEFEAT, GameOutcome.DEFEAT},
    ]

    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)

    assert ranks == [0, 1]  # first team won


def test_team_outcome_victory_has_priority_over_draw():
    team_outcomes = [
        {GameOutcome.VICTORY, GameOutcome.DRAW},
        {GameOutcome.DRAW, GameOutcome.DEFEAT},
    ]

    ranks = GameRater._ranks_from_team_outcomes(team_outcomes)

    assert ranks == [0, 1]  # first team won


def test_team_outcome_no_double_victory():
    team_outcomes = [
        {GameOutcome.VICTORY, GameOutcome.VICTORY},
        {GameOutcome.VICTORY, GameOutcome.DEFEAT},
    ]

    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)


def test_team_outcome_unranked_if_ambiguous():
    team_outcomes = [
        {GameOutcome.UNKNOWN, GameOutcome.DEFEAT},
        {GameOutcome.DEFEAT, GameOutcome.DEFEAT},
    ]

    with pytest.raises(GameRatingError):
        GameRater._ranks_from_team_outcomes(team_outcomes)


def test_ranks_to_clean_outcomes():
    assert GameRater._ranks_to_clean_outcomes([0, 0]) == [
        GameOutcome.DRAW,
        GameOutcome.DRAW,
    ]
    assert GameRater._ranks_to_clean_outcomes([1, 0]) == [
        GameOutcome.DEFEAT,
        GameOutcome.VICTORY,
    ]
    assert GameRater._ranks_to_clean_outcomes([0, 1]) == [
        GameOutcome.VICTORY,
        GameOutcome.DEFEAT,
    ]


def test_compute_rating_1v1(rating_data_1v1):
    old_ratings = {
        player_id: data.rating
        for team in rating_data_1v1
        for player_id, data in team.items()
    }

    new_ratings, outcomes = GameRater.compute_rating(rating_data_1v1)

    assert outcomes[1] is GameOutcome.VICTORY
    assert outcomes[2] is GameOutcome.DEFEAT

    assert new_ratings[1] > old_ratings[1]
    assert new_ratings[2] < old_ratings[2]

    assert new_ratings[1].sigma < old_ratings[1].sigma
    assert new_ratings[2].sigma < old_ratings[2].sigma


def test_compute_rating_2v2(rating_data_2v2):
    old_ratings = {
        player_id: data.rating
        for team in rating_data_2v2
        for player_id, data in team.items()
    }

    new_ratings, outcomes = GameRater.compute_rating(rating_data_2v2)

    assert outcomes[1] is GameOutcome.VICTORY
    assert outcomes[2] is GameOutcome.VICTORY
    assert outcomes[3] is GameOutcome.DEFEAT
    assert outcomes[4] is GameOutcome.DEFEAT

    assert new_ratings[1] > old_ratings[1]
    assert new_ratings[2] > old_ratings[2]
    assert new_ratings[3] < old_ratings[3]
    assert new_ratings[4] < old_ratings[4]

    assert new_ratings[1].sigma < old_ratings[1].sigma
    assert new_ratings[2].sigma < old_ratings[2].sigma
    assert new_ratings[3].sigma < old_ratings[3].sigma
    assert new_ratings[4].sigma < old_ratings[4].sigma
