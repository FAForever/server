from typing import Optional

import pytest

from server.games.game_results import (
    ArmyOutcome,
    GameOutcome,
    GameResolutionError,
    resolve_game
)


class ResolutionTest:
    resolution: Optional[list[GameOutcome]]

    def __init__(self, resolution: Optional[list[GameOutcome]]):
        self.resolution = resolution

    def __call__(self, partial_outcomes: list[set[ArmyOutcome]]):
        if self.resolution is None:
            with pytest.raises(GameResolutionError):
                resolve_game(partial_outcomes)
        else:
            assert resolve_game(partial_outcomes) == self.resolution


resolve_to_error = ResolutionTest(None)
resolve_to_win = ResolutionTest([GameOutcome.VICTORY, GameOutcome.DEFEAT])
resolve_to_draw = ResolutionTest([GameOutcome.DRAW, GameOutcome.DRAW])
resolve_to_loss = ResolutionTest([GameOutcome.DEFEAT, GameOutcome.VICTORY])


def test_only_rate_with_two_parties():
    one_party = [{ArmyOutcome.VICTORY}]
    two_parties = [{ArmyOutcome.VICTORY}, {ArmyOutcome.DEFEAT}]
    three_parties = [
        {ArmyOutcome.VICTORY},
        {ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT}
    ]

    resolve_to_error(one_party)
    resolve_to_error(three_parties)
    resolve_game(two_parties)


def testresolve():
    team_outcomes = [{ArmyOutcome.VICTORY}, {ArmyOutcome.DEFEAT}]
    resolve_to_win(team_outcomes)


def test_ranks_all_1v1_possibilities():
    """
    Document expectations for all outcomes of 1v1 games.
    With six possible outcomes there are 36 possibilities.
    """

    err_, win_, draw, loss = (resolve_to_error, resolve_to_win, resolve_to_draw, resolve_to_loss)
    #        Victory     Recall      Unknown
    #              Defeat      Draw        Conflicting
    grid = [[err_, win_, win_, win_, win_, win_],  # Victory
            [loss, draw, draw, err_, err_, err_],  # Defeat
            [loss, draw, draw, err_, err_, err_],  # Recall
            [loss, err_, err_, draw, err_, err_],  # Draw
            [loss, err_, err_, err_, err_, err_],  # Unknown
            [loss, err_, err_, err_, err_, err_]]  # Conflicting
    outcome_list = list(ArmyOutcome)
    assert len(outcome_list) == len(grid) == len(grid[0])

    for outcome1, row in enumerate(grid):
        for outcome2, resolution in enumerate(row):
            team_outcomes = [{outcome_list[outcome1]}, {outcome_list[outcome2]}]
            resolution(team_outcomes)


def test_team_outcome_ignores_unknown():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.UNKNOWN},
        {ArmyOutcome.DEFEAT, ArmyOutcome.UNKNOWN},
    ]
    resolve_to_win(team_outcomes)


def test_team_outcome_throws_if_unilateral_draw():
    team_outcomes = [
        {ArmyOutcome.DRAW, ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT, ArmyOutcome.UNKNOWN},
    ]
    resolve_to_error(team_outcomes)


def test_team_outcome_victory_has_priority_over_defeat():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT, ArmyOutcome.DEFEAT},
    ]
    resolve_to_win(team_outcomes)


def test_team_outcome_victory_has_priority_over_draw():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.DRAW},
        {ArmyOutcome.DRAW, ArmyOutcome.DEFEAT},
    ]
    resolve_to_win(team_outcomes)


def test_team_outcome_no_double_victory():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.VICTORY},
        {ArmyOutcome.VICTORY, ArmyOutcome.DEFEAT},
    ]
    resolve_to_error(team_outcomes)


def test_team_outcome_unranked_if_ambiguous():
    team_outcomes = [
        {ArmyOutcome.UNKNOWN, ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT, ArmyOutcome.DEFEAT},
    ]
    resolve_to_error(team_outcomes)
