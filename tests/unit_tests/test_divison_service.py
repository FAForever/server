# coding=utf-8
from unittest.mock import MagicMock

import pytest
from server.stats.division_service import *


@pytest.fixture()
def sample_divisions() -> List[Division]:
    return [Division(1, "League 1 - Division A", 1, 10.0),
            Division(2, "League 1 - Division B", 1, 30.0),
            Division(3, "League 1 - Division C", 1, 50.0),
            Division(4, "League 2 - Division D", 2, 20.0),
            Division(5, "League 2 - Division E", 2, 60.0),
            Division(6, "League 2 - Division F", 2, 100.0),
            Division(7, "League 3 - Division D", 3, 100.0),
            Division(8, "League 3 - Division E", 3, 200.0),
            Division(9, "League 3 - Division F", 3, 9999.0)]


@pytest.fixture()
def sample_players() -> List[PlayerDivisionInfo]:
    return [PlayerDivisionInfo(1, 1, 9.5),
            PlayerDivisionInfo(2, 1, 49.5),
            PlayerDivisionInfo(3, 2, 0.0),
            PlayerDivisionInfo(4, 3, 10.0)]


@pytest.fixture()
def division_service(sample_divisions, sample_players) -> DivisionService:
    return DivisionService(sample_divisions, sample_players, MagicMock())


def test_match_in_same_division(division_service):
    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.5
    assert division_service.get_player_division(1).id == 1
    assert division_service.players[2].league == 1
    assert division_service.players[2].score == 49.5
    assert division_service.get_player_division(2).id == 3

    division_service.post_result(1,2, 1)

    division_service.persistor.add_player.assert_not_called()
    division_service.persistor.update_player.assert_any_call(division_service.players[1])
    division_service.persistor.update_player.assert_any_call(division_service.players[2])

    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 10.5
    assert division_service.get_player_division(1).id == 2
    assert division_service.players[2].league == 1
    assert division_service.players[2].score == 49.0
    assert division_service.get_player_division(2).id == 3


def test_match_in_same_division_inverted(division_service):
    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.5
    assert division_service.get_player_division(1).id == 1
    assert division_service.players[2].league == 1
    assert division_service.players[2].score == 49.5
    assert division_service.get_player_division(2).id == 3

    division_service.post_result(2,1, 2)

    division_service.persistor.add_player.assert_not_called()
    division_service.persistor.update_player.assert_any_call(division_service.players[1])
    division_service.persistor.update_player.assert_any_call(division_service.players[2])

    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 10.5
    assert division_service.get_player_division(1).id == 2
    assert division_service.players[2].league == 1
    assert division_service.players[2].score == 49.0
    assert division_service.get_player_division(2).id == 3


def test_match_winner_ascends_league(division_service):
    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.5
    assert division_service.get_player_division(1).id == 1
    assert division_service.players[2].league == 1
    assert division_service.players[2].score == 49.5
    assert division_service.get_player_division(2).id == 3

    division_service.post_result(2,1, 1)

    division_service.persistor.add_player.assert_not_called()
    division_service.persistor.update_player.assert_any_call(division_service.players[1])
    division_service.persistor.update_player.assert_any_call(division_service.players[2])

    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.0
    assert division_service.get_player_division(1).id == 1
    assert division_service.players[2].league == 2
    assert division_service.players[2].score == 0.0
    assert division_service.get_player_division(2).id == 4


def test_do_not_fall_below_0(division_service):
    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.5
    assert division_service.players[3].league == 2
    assert division_service.players[3].score == 0.0

    division_service.post_result(1,3, 1)

    division_service.persistor.add_player.assert_not_called()
    division_service.persistor.update_player.assert_any_call(division_service.players[1])
    division_service.persistor.update_player.assert_any_call(division_service.players[3])

    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 11.0
    assert division_service.players[3].league == 2
    assert division_service.players[3].score == 0.0


def test_gain_loss_winner_inferior(division_service):
    division_service.players[3].score = 11.0

    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.5
    assert division_service.players[3].league == 2
    assert division_service.players[3].score == 11.0

    division_service.post_result(1,3, 1)

    division_service.persistor.add_player.assert_not_called()
    division_service.persistor.update_player.assert_any_call(division_service.players[1])
    division_service.persistor.update_player.assert_any_call(division_service.players[3])

    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 11.0
    assert division_service.players[3].league == 2
    assert division_service.players[3].score == 10.0


def test_gain_loss_winner_superior(division_service):
    division_service.players[3].score = 11.0

    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.5
    assert division_service.players[3].league == 2
    assert division_service.players[3].score == 11.0

    division_service.post_result(1,3, 2)

    division_service.persistor.add_player.assert_not_called()
    division_service.persistor.update_player.assert_any_call(division_service.players[1])
    division_service.persistor.update_player.assert_any_call(division_service.players[3])

    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.0
    assert division_service.players[3].league == 2
    assert division_service.players[3].score == 11.5


def test_new_player(division_service):
    assert 98 not in division_service.players
    assert 99 not in division_service.players

    division_service.post_result(98,99, 2)

    assert division_service.persistor.add_player.call_count == 2
    assert division_service.persistor.update_player.call_count == 2

    assert division_service.players[98].league == 1
    assert division_service.players[98].score == 0.0
    assert division_service.players[99].league == 1
    assert division_service.players[99].score == 1.0


def test_draw(division_service):
    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.5
    assert division_service.get_player_division(1).id == 1
    assert division_service.players[2].league == 1
    assert division_service.players[2].score == 49.5
    assert division_service.get_player_division(2).id == 3

    division_service.post_result(1,2, 0)

    division_service.persistor.add_player.assert_not_called()
    division_service.persistor.update_player.assert_any_call(division_service.players[1])
    division_service.persistor.update_player.assert_any_call(division_service.players[2])

    assert division_service.players[1].league == 1
    assert division_service.players[1].score == 9.5
    assert division_service.get_player_division(1).id == 1
    assert division_service.players[2].league == 1
    assert division_service.players[2].score == 49.5
    assert division_service.get_player_division(2).id == 3