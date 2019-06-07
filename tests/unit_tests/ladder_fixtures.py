from unittest import mock


import pytest

from server import LadderService
from server.players import Player


@pytest.fixture()
def map_pool():
    return [(1, '', 'scmp_001'), (5, '', 'scmp_05'), (10, '', 'scmp_010'), (12, '', 'scmp_012'), (11, '', 'scmp_0011')]


def playerMock(lobbythread, id):
    player_mock = mock.create_autospec(spec=Player(''))
    player_mock.login = "Player %s" % id
    player_mock.id = id
    player_mock.lobby_connection = lobbythread
    return player_mock


@pytest.fixture()
def player1(lobbythread):
    return playerMock(lobbythread, 1)


@pytest.fixture()
def player2(lobbythread):
    return playerMock(lobbythread, 2)


@pytest.fixture()
def ladder_setup(player1, player2, map_pool):
    return {
        'player1': player1,
        'player2': player2,
        'map_pool': map_pool
    }
