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


def test_team_outcome():
    p1, p2 = MockPlayer(), MockPlayer()
    players_by_team = {2: [p1], 3: [p2]}
    outcome_py_player = {p1: GameOutcome.VICTORY, p2: GameOutcome.DEFEAT}

    rater = GameRater(players_by_team, outcome_py_player)
    assert rater._get_team_outcome([p1]) is GameOutcome.VICTORY
    assert rater._get_team_outcome([p2]) is GameOutcome.DEFEAT


def test_team_outcome_ignores_unknown():
    p1, p2, p3, p4 = MockPlayer(), MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {2: [p1, p2], 3: [p3, p4]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.UNKNOWN,
        p3: GameOutcome.DEFEAT,
        p4: GameOutcome.UNKNOWN
    }

    rater = GameRater(players_by_team, outcome_py_player)
    assert rater._get_team_outcome(players_by_team[2]) is GameOutcome.VICTORY
    assert rater._get_team_outcome(players_by_team[3]) is GameOutcome.DEFEAT


def test_team_outcome_throws_if_inconsistent():
    p1, p2, p3, p4 = MockPlayer(), MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {2: [p1, p2], 3: [p3, p4]}
    outcome_py_player = {
        p1: GameOutcome.MUTUAL_DRAW,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
        p4: GameOutcome.DRAW
    }

    rater = GameRater(players_by_team, outcome_py_player)
    with pytest.raises(GameRatingError):
        rater._get_team_outcome(players_by_team[2])
    with pytest.raises(GameRatingError):
        rater._get_team_outcome(players_by_team[3])


def test_team_outcome_victory_has_priority():
    p1, p2, p3, p4 = MockPlayer(), MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {2: [p1, p2], 3: [p3, p4]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
        p4: GameOutcome.DEFEAT
    }

    rater = GameRater(players_by_team, outcome_py_player)
    assert rater._get_team_outcome(players_by_team[2]) is GameOutcome.VICTORY
    assert rater._get_team_outcome(players_by_team[3]) is GameOutcome.DEFEAT


def test_ranks():
    rater = GameRater({}, {})
    assert rater._ranks_from_team_outcomes([GameOutcome.VICTORY, GameOutcome.DEFEAT]) == [0, 1]
    assert rater._ranks_from_team_outcomes([GameOutcome.DEFEAT, GameOutcome.VICTORY]) == [1, 0]


def test_ranks_with_unknown():
    rater = GameRater({}, {})
    assert rater._ranks_from_team_outcomes([GameOutcome.UNKNOWN, GameOutcome.DEFEAT]) == [0, 1]
    assert rater._ranks_from_team_outcomes([GameOutcome.VICTORY, GameOutcome.UNKNOWN]) == [0, 1]
    assert rater._ranks_from_team_outcomes([GameOutcome.UNKNOWN, GameOutcome.VICTORY]) == [1, 0]
    assert rater._ranks_from_team_outcomes([GameOutcome.DEFEAT, GameOutcome.UNKNOWN]) == [1, 0]
    with pytest.raises(GameRatingError):
        rater._ranks_from_team_outcomes([GameOutcome.UNKNOWN, GameOutcome.UNKNOWN])


def test_ranks_with_double_victory_is_inconsistent():
    rater = GameRater({}, {})
    with pytest.raises(GameRatingError):
        rater._ranks_from_team_outcomes([GameOutcome.VICTORY, GameOutcome.VICTORY])


def test_ranks_with_double_defeat_treated_as_draw():
    rater = GameRater({}, {})
    assert rater._ranks_from_team_outcomes([GameOutcome.DEFEAT, GameOutcome.DEFEAT]) == [0, 0]


def test_ranks_with_draw():
    rater = GameRater({}, {})

    assert rater._ranks_from_team_outcomes([GameOutcome.DRAW, GameOutcome.DRAW]) == [0, 0]
    assert rater._ranks_from_team_outcomes([GameOutcome.MUTUAL_DRAW, GameOutcome.MUTUAL_DRAW]) == [0, 0]

    with pytest.raises(GameRatingError):
        rater._ranks_from_team_outcomes([GameOutcome.VICTORY, GameOutcome.DRAW])
    with pytest.raises(GameRatingError):
        rater._ranks_from_team_outcomes([GameOutcome.DEFEAT, GameOutcome.DRAW])
    with pytest.raises(GameRatingError):
        rater._ranks_from_team_outcomes([GameOutcome.UNKNOWN, GameOutcome.DRAW])


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
