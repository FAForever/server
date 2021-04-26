import logging
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


def test_metadata_no_matching_army(game_results):
    assert game_results.metadata(1) == []


def test_no_metadata_for_army(game_results):
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10))

    assert game_results.metadata(1) == []


def test_matching_simple_metadata(game_results):
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall"))

    assert game_results.metadata(1) == ["recall"]


def test_matching_complex_metadata(game_results):
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall something else"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall something else"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall something else"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall something else"))

    assert game_results.metadata(1) == ["else", "recall", "something"]


def test_conflicting_simple_metadata(game_results, caplog):
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "something"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "else"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall"))

    with caplog.at_level(logging.INFO):
        assert game_results.metadata(1) == []
        assert "Conflicting metadata" in caplog.records[0].message


def test_conflicting_complex_metadata(game_results, caplog):
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall something else"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall other thing"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, "recall thing"))
    game_results.add(GameResultReport(1, 1, ArmyReportedOutcome.DEFEAT, -10, ""))

    with caplog.at_level(logging.INFO):
        assert game_results.metadata(1) == ["recall"]
        assert "Conflicting metadata" in caplog.records[0].message
