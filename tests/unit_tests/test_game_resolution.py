import pytest

from server.games.game_results import (
    ArmyOutcome,
    GameOutcome,
    GameResolutionError,
    resolve_game
)
from typing import Optional


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


ResolveError = ResolutionTest(None)
ResolveWin = ResolutionTest([GameOutcome.VICTORY, GameOutcome.DEFEAT])
ResolveDraw = ResolutionTest([GameOutcome.DRAW, GameOutcome.DRAW])
ResolveLoss = ResolutionTest([GameOutcome.DEFEAT, GameOutcome.VICTORY])


def test_only_rate_with_two_parties():
    one_party = [{ArmyOutcome.VICTORY}]
    two_parties = [{ArmyOutcome.VICTORY}, {ArmyOutcome.DEFEAT}]
    three_parties = [
        {ArmyOutcome.VICTORY},
        {ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT}
    ]

    ResolveError(one_party)
    ResolveError(three_parties)
    resolve_game(two_parties)


def testresolve():
    team_outcomes = [{ArmyOutcome.VICTORY}, {ArmyOutcome.DEFEAT}]
    ResolveWin(team_outcomes)


def test_ranks_all_1v1_possibilities():
    """
    Document expectations for all outcomes of 1v1 games.
    With six possible outcomes there are 36 possibilities.
    """

    ERR_ = ResolveError
    WIN_ = ResolveWin
    DRAW = ResolveDraw
    LOSS = ResolveLoss
    #        Victory     Recall      Unknown
    #              Defeat      Draw        Conflicting
    grid = [[ERR_, WIN_, WIN_, WIN_, WIN_, WIN_],  # Victory
            [LOSS, DRAW, DRAW, ERR_, ERR_, ERR_],  # Defeat
            [LOSS, DRAW, DRAW, ERR_, ERR_, ERR_],  # Recall
            [LOSS, ERR_, ERR_, DRAW, ERR_, ERR_],  # Draw
            [LOSS, ERR_, ERR_, ERR_, ERR_, ERR_],  # Unknown
            [LOSS, ERR_, ERR_, ERR_, ERR_, ERR_]]  # Conflicting
    outcome_list = [o for o in ArmyOutcome]

    for outcome1, row in enumerate(grid):
        for outcome2, Resolution in enumerate(row):
            team_outcomes = [{outcome_list[outcome1]}, {outcome_list[outcome2]}]
            Resolution(team_outcomes)


def test_team_outcome_ignores_unknown():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.UNKNOWN},
        {ArmyOutcome.DEFEAT, ArmyOutcome.UNKNOWN},
    ]
    ResolveWin(team_outcomes)


def test_team_outcome_throws_if_unilateral_draw():
    team_outcomes = [
        {ArmyOutcome.DRAW, ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT, ArmyOutcome.UNKNOWN},
    ]
    ResolveError(team_outcomes)


def test_team_outcome_victory_has_priority_over_defeat():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT, ArmyOutcome.DEFEAT},
    ]
    ResolveWin(team_outcomes)


def test_team_outcome_victory_has_priority_over_draw():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.DRAW},
        {ArmyOutcome.DRAW, ArmyOutcome.DEFEAT},
    ]
    ResolveWin(team_outcomes)


def test_team_outcome_no_double_victory():
    team_outcomes = [
        {ArmyOutcome.VICTORY, ArmyOutcome.VICTORY},
        {ArmyOutcome.VICTORY, ArmyOutcome.DEFEAT},
    ]
    ResolveError(team_outcomes)


def test_team_outcome_unranked_if_ambiguous():
    team_outcomes = [
        {ArmyOutcome.UNKNOWN, ArmyOutcome.DEFEAT},
        {ArmyOutcome.DEFEAT, ArmyOutcome.DEFEAT},
    ]
    ResolveError(team_outcomes)
