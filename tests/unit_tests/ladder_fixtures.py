from unittest import mock


from PySide import QtSql
import pytest

from server.games import Ladder1V1GamesContainer
from server.players import Player


@pytest.fixture()
def map_pool():
    return {1, 5, 10, 12, 15}

def playerMock(lobbythread, id):
    player_mock = mock.create_autospec(spec=Player(''))
    player_mock.login = "Player %s" % id
    player_mock.id = id
    player_mock.game_port = 4242
    player_mock.lobbyThread = lobbythread
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

@pytest.fixture()
def container(db, monkeypatch, sqlquery, game_service):
    monkeypatch.setattr(QtSql, 'QSqlQuery', sqlquery)
    return Ladder1V1GamesContainer(db, game_service)
