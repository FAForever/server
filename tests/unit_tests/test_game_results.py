import mock
import pytest

from server.games.game_results import (
    ArmyOutcome,
    ArmyReportedOutcome,
    GameResultReport,
    GameResultReports
)


@pytest.fixture
def game_results():
    return GameResultReports(game_id=42)


def test_reported_result_to_resolved():
    assert ArmyReportedOutcome.VICTORY.to_resolved() is ArmyOutcome.VICTORY
    assert ArmyReportedOutcome.DEFEAT.to_resolved() is ArmyOutcome.DEFEAT
    assert ArmyReportedOutcome.DRAW.to_resolved() is ArmyOutcome.DRAW
    assert ArmyReportedOutcome.MUTUAL_DRAW.to_resolved() is ArmyOutcome.DRAW

    # Make sure our test hits every enum variant in case new ones are added
    for variant in ArmyReportedOutcome:
        assert variant.to_resolved() in ArmyOutcome


def test_outcome_cache(game_results):
    game_results._compute_outcome = mock.Mock(
        side_effect=game_results._compute_outcome
    )
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10))

    assert game_results.outcome(1) is ArmyOutcome.DEFEAT
    game_results._compute_outcome.assert_called_once_with(1)
    assert game_results.outcome(1) is ArmyOutcome.DEFEAT
    game_results._compute_outcome.assert_called_once_with(1)
    game_results._compute_outcome.reset_mock()

    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.VICTORY, -10))
    assert game_results.outcome(1) is ArmyOutcome.CONFLICTING
    game_results._compute_outcome.assert_called_once_with(1)
    assert game_results.outcome(1) is ArmyOutcome.CONFLICTING
    game_results._compute_outcome.assert_called_once_with(1)
