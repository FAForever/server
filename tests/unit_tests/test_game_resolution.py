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
    Assumes that the order of teams doesn't matter.
    With five possible outcomes there are 15 possibilities.
    """
    team_outcomes = [{ArmyOutcome.VICTORY}, {ArmyOutcome.VICTORY}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{ArmyOutcome.VICTORY}, {ArmyOutcome.DEFEAT}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]

    team_outcomes = [{ArmyOutcome.VICTORY}, {ArmyOutcome.DRAW}]
    resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]

    team_outcomes = [{ArmyOutcome.VICTORY}, {ArmyOutcome.UNKNOWN}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]

    team_outcomes = [{ArmyOutcome.VICTORY}, {ArmyOutcome.CONFLICTING}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]

    team_outcomes = [{ArmyOutcome.DEFEAT}, {ArmyOutcome.DEFEAT}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.DRAW, GameOutcome.DRAW]

    team_outcomes = [{ArmyOutcome.DEFEAT}, {ArmyOutcome.DRAW}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{ArmyOutcome.DEFEAT}, {ArmyOutcome.UNKNOWN}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{ArmyOutcome.DEFEAT}, {ArmyOutcome.CONFLICTING}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{ArmyOutcome.DRAW}, {ArmyOutcome.DRAW}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.DRAW, GameOutcome.DRAW]

    team_outcomes = [{ArmyOutcome.DRAW}, {ArmyOutcome.UNKNOWN}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{ArmyOutcome.DRAW}, {ArmyOutcome.CONFLICTING}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{ArmyOutcome.UNKNOWN}, {ArmyOutcome.UNKNOWN}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{ArmyOutcome.UNKNOWN}, {ArmyOutcome.CONFLICTING}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{ArmyOutcome.CONFLICTING}, {ArmyOutcome.CONFLICTING}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)


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
