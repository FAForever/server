import pytest
from server.games.game_rater import GameRater, GameRatingError
from server.games.game_results import GameOutcome
from server.rating import RatingType
from trueskill import Rating


class MockPlayer:
    ratings = {RatingType.GLOBAL: (1500, 500), RatingType.LADDER_1V1: (1500, 500)}


def test_get_rating_groups():
    p1, p2 = MockPlayer(), MockPlayer()
    players_by_team = {2: [p1], 3: [p2]}
    outcome_py_player = {p1: GameOutcome.VICTORY, p2: GameOutcome.DEFEAT}

    rater = GameRater(players_by_team, outcome_py_player)
    rating_groups = rater._get_rating_groups()

    assert len(rating_groups) == 2
    assert {p1: Rating(1500, 500)} in rating_groups


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


def test_compute_rating():
    p1, p2 = MockPlayer(), MockPlayer()
    players_by_team = {2: [p1], 3: [p2]}
    outcome_py_player = {p1: GameOutcome.VICTORY, p2: GameOutcome.DEFEAT}

    rater = GameRater(players_by_team, outcome_py_player)
    result = rater.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


def test_compute_rating_of_two_player_ffa_match_if_one_chose_a_team():
    FFA_TEAM = 1
    p1, p2 = MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1], 2: [p2]}
    outcome_py_player = {p1: GameOutcome.VICTORY, p2: GameOutcome.DEFEAT}

    rater = GameRater(players_by_team, outcome_py_player)
    result = rater.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


def test_compute_rating_for_single_ffa_player_vs_a_team():
    FFA_TEAM = 1
    p1, p2, p3 = MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1], 2: [p2, p3]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
    }

    rater = GameRater(players_by_team, outcome_py_player)
    result = rater.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


def test_compute_rating_of_two_player_ffa_match_if_none_chose_a_team():
    FFA_TEAM = 1
    p1, p2 = MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1, p2]}
    outcome_py_player = {p1: GameOutcome.VICTORY, p2: GameOutcome.DEFEAT}

    rater = GameRater(players_by_team, outcome_py_player)
    result = rater.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


def test_dont_rate_partial_ffa_matches():
    FFA_TEAM = 1
    p1, p2, p3, p4 = MockPlayer(), MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1, p3], 2: [p2, p4]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
        p4: GameOutcome.DEFEAT,
    }

    rater = GameRater(players_by_team, outcome_py_player)
    with pytest.raises(GameRatingError):
        rater.compute_rating()


def test_dont_rate_pure_ffa_matches_with_more_than_two_players():
    FFA_TEAM = 1
    p1, p2, p3 = MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1, p2, p3]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
    }

    rater = GameRater(players_by_team, outcome_py_player)
    with pytest.raises(GameRatingError):
        rater.compute_rating()


def test_dont_rate_threeway_team_matches():
    p1, p2, p3 = MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {2: [p1], 3: [p2], 4: [p3]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
    }

    rater = GameRater(players_by_team, outcome_py_player)
    with pytest.raises(GameRatingError):
        rater.compute_rating()
