import pytest

from server.games.game_results import (
    ArmyOutcome,
    GameOutcome,
    GameResolutionError,
    resolve_game
)


def test_only_rate_with_two_parties():
    one_party = [{ArmyOutcome.VICTORY}]
    two_parties = [{ArmyOutcome.VICTORY}, {ArmyOutcome.DEFEAT}]
    three_parties = [
        {ArmyOutcome.VICTORY},
        {ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT}
    ]

    with pytest.raises(GameResolutionError):
        resolve_game(one_party)

    with pytest.raises(GameResolutionError):
        resolve_game(three_parties)

    resolve_game(two_parties)


def testresolve():
    team_outcomes = [{ArmyOutcome.VICTORY}, {ArmyOutcome.DEFEAT}]

    ranks = resolve_game(team_outcomes)

    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]


def test_ranks_all_1v1_possibilities():
    """
    Document expectations for all outcomes of 1v1 games.
    With six possible outcomes there are 36 possibilities.
    """

    ERROR = 0
    DRAW = 1
    WIN = 2
    LOSS = 3
    #        Victory  Defeat   Recall   Draw     Unknown  Conflicting
    grid = [[ERROR,   WIN,     WIN,     WIN,     WIN,     WIN  ]  # Victory
            [LOSS,    DRAW,    DRAW,    ERROR,   ERROR,   ERROR]  # Defeat
            [LOSS,    DRAW,    DRAW,    ERROR,   ERROR,   ERROR]  # Recall
            [LOSS,    ERROR,   ERROR,   DRAW,    ERROR,   ERROR]  # Draw
            [LOSS,    ERROR,   ERROR,   ERROR,   ERROR,   ERROR]  # Unknown
            [LOSS,    ERROR,   ERROR,   ERROR,   ERROR,   ERROR]] # Conflicting
    outcome_list = [ArmyOutcome.VICTORY, ArmyOutcome.DEFEAT, ArmyOutcome.RECALL,
            ArmyOutcome.DRAW, ArmyOutcome.UNKNOWN, ArmyOutcome.CONFLICTING]

    win_resolution = [GameOutcome.VICTORY, GameOutcome.DEFEAT]
    draw_resolution = [GameOutcome.DRAW, GameOutcome.DRAW]
    loss_resolution = [GameOutcome.DEFEAT, GameOutcome.VICTORY]

    for outcome1, row in grid:
        for outcome2, resolution in row:
            team_outcomes = [{outcome_list[outcome1]}, {outcome_list[outcome2]}]
            if resolution == ERROR:
                with pytest.raises(GameResolutionError):
                    resolve_game(team_outcomes)
            elif resolution == WIN:
                assert resolve_game(team_outcomes) == win_resolution
            elif resolution == DRAW:
                assert resolve_game(team_outcomes) == draw_resolution
            elif resolution == LOSS:
                assert resolve_game(team_outcomes) == loss_resolution


def test_team_outcome_ignores_unknown():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.UNKNOWN},
        {ArmyOutcome.DEFEAT, ArmyOutcome.UNKNOWN},
    ]

    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]


def test_team_outcome_throws_if_unilateral_draw():
    team_outcomes = [
        {ArmyOutcome.DRAW, ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT, ArmyOutcome.UNKNOWN},
    ]

    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)


def test_team_outcome_victory_has_priority_over_defeat():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT, ArmyOutcome.DEFEAT},
    ]

    ranks = resolve_game(team_outcomes)

    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]


def test_team_outcome_victory_has_priority_over_draw():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.DRAW},
        {ArmyOutcome.DRAW, ArmyOutcome.DEFEAT},
    ]

    ranks = resolve_game(team_outcomes)

    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]


def test_team_outcome_no_double_victory():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.VICTORY},
        {ArmyOutcome.VICTORY, ArmyOutcome.DEFEAT},
    ]

    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)


def test_team_outcome_unranked_if_ambiguous():
    team_outcomes = [
        {ArmyOutcome.UNKNOWN, ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT, ArmyOutcome.DEFEAT},
    ]

    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)
