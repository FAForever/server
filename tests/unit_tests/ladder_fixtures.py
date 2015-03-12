from games import ladderGamesContainer, ladder1v1GamesContainerClass
from PySide import QtSql
from unittest import mock

import pytest
from src.players import Player


@pytest.fixture()
def popular_maps():
    return [1, 5, 10, 12, 15]


@pytest.fixture()
def player1_maps():
    return [1, 3, 5, 7, 8]


@pytest.fixture()
def player2_maps():
    return [2, 4, 6, 9]


def playerMock(lobbythread, id):
    player_mock = mock.Mock(spec=Player)
    player_mock.getLogin = lambda: "Player %s" % id
    player_mock.setAction = lambda action: None
    player_mock.getId = lambda: id
    player_mock.setWantGame = lambda bool: None
    player_mock.setGame = lambda uid: None
    player_mock.getGamePort = lambda: 4242
    player_mock.getLeague = lambda: 'derp'
    player_mock.getLobbyThread = lambda: lobbythread
    return player_mock


@pytest.fixture()
def player1(lobbythread):
    return playerMock(lobbythread, 1)


@pytest.fixture()
def player2(lobbythread):
    return playerMock(lobbythread, 2)


@pytest.fixture()
def ladder_setup(player1, player2, player1_maps, player2_maps, popular_maps):
    return {
        'player1': player1,
        'player2': player2,
        'player1_maps': player1_maps,
        'player2_maps': player2_maps,
        'popular_maps': popular_maps
    }


@pytest.fixture()
def container(db, monkeypatch, sqlquery):
    monkeypatch.setattr(QtSql, 'QSqlQuery', sqlquery)
    return ladder1v1GamesContainerClass(db)
