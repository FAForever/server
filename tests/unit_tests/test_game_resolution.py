import pytest

from server.games.game_results import (
    GameOutcome,
    GameResolutionError,
    resolve_game
)


def test_only_rate_with_two_parties():
    one_party = [{GameOutcome.VICTORY}]
    two_parties = [{GameOutcome.VICTORY}, {GameOutcome.DEFEAT}]
    three_parties = [{GameOutcome.VICTORY}, {GameOutcome.DEFEAT}, {GameOutcome.DEFEAT}]

    with pytest.raises(GameResolutionError):
        resolve_game(one_party)

    with pytest.raises(GameResolutionError):
        resolve_game(three_parties)

    resolve_game(two_parties)


def testresolve():
    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.DEFEAT}]

    ranks = resolve_game(team_outcomes)

    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]


def test_ranks_all_1v1_possibilities():
    """
    Document expectations for all outcomes of 1v1 games.
    Assumes that the order of teams doesn't matter.
    With six possible outcomes there are 21 possibilities.
    """
    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.VICTORY}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.DEFEAT}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.DRAW}]
    resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.MUTUAL_DRAW}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.UNKNOWN}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]

    team_outcomes = [{GameOutcome.VICTORY}, {GameOutcome.CONFLICTING}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]

    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.DEFEAT}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.DRAW, GameOutcome.DRAW]

    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.DRAW}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.MUTUAL_DRAW}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.UNKNOWN}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.DEFEAT}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.DRAW}, {GameOutcome.DRAW}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.DRAW, GameOutcome.DRAW]

    team_outcomes = [{GameOutcome.DRAW}, {GameOutcome.MUTUAL_DRAW}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.DRAW, GameOutcome.DRAW]

    team_outcomes = [{GameOutcome.DRAW}, {GameOutcome.UNKNOWN}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.DRAW}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.MUTUAL_DRAW}, {GameOutcome.MUTUAL_DRAW}]
    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.DRAW, GameOutcome.DRAW]

    team_outcomes = [{GameOutcome.MUTUAL_DRAW}, {GameOutcome.UNKNOWN}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.MUTUAL_DRAW}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.UNKNOWN}, {GameOutcome.UNKNOWN}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.UNKNOWN}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)

    team_outcomes = [{GameOutcome.CONFLICTING}, {GameOutcome.CONFLICTING}]
    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)


def test_team_outcome_ignores_unknown():
    team_outcomes = [
        {GameOutcome.VICTORY, GameOutcome.UNKNOWN},
        {GameOutcome.DEFEAT, GameOutcome.UNKNOWN},
    ]

    ranks = resolve_game(team_outcomes)
    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]


def test_team_outcome_throws_if_unilateral_draw():
    team_outcomes = [
        {GameOutcome.DRAW, GameOutcome.DEFEAT},
        {GameOutcome.DEFEAT, GameOutcome.UNKNOWN},
    ]

    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)


def test_team_outcome_throws_if_unilateral_mutual_draw():
    team_outcomes = [
        {GameOutcome.MUTUAL_DRAW, GameOutcome.DEFEAT},
        {GameOutcome.DEFEAT, GameOutcome.UNKNOWN},
    ]

    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)


def test_team_outcome_victory_has_priority_over_defeat():
    team_outcomes = [
        {GameOutcome.VICTORY, GameOutcome.DEFEAT},
        {GameOutcome.DEFEAT, GameOutcome.DEFEAT},
    ]

    ranks = resolve_game(team_outcomes)

    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]


def test_team_outcome_victory_has_priority_over_draw():
    team_outcomes = [
        {GameOutcome.VICTORY, GameOutcome.DRAW},
        {GameOutcome.DRAW, GameOutcome.DEFEAT},
    ]

    ranks = resolve_game(team_outcomes)

    assert ranks == [GameOutcome.VICTORY, GameOutcome.DEFEAT]


def test_team_outcome_no_double_victory():
    team_outcomes = [
        {GameOutcome.VICTORY, GameOutcome.VICTORY},
        {GameOutcome.VICTORY, GameOutcome.DEFEAT},
    ]

    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)


def test_team_outcome_unranked_if_ambiguous():
    team_outcomes = [
        {GameOutcome.UNKNOWN, GameOutcome.DEFEAT},
        {GameOutcome.DEFEAT, GameOutcome.DEFEAT},
    ]

    with pytest.raises(GameResolutionError):
        resolve_game(team_outcomes)
