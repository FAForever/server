from gameModes import ladderGamesContainer, ladder1v1GamesContainerClass

from PySide import QtSql

import pytest
from flexmock import flexmock

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
    return flexmock(
        getLogin=lambda: "Player %s" % id,
        setAction=lambda action: None,
        getId=lambda: id,
        setWantGame=lambda bool: None,
        setGame=lambda uid: None,
        getGamePort=lambda: 4242,
        getLeague=lambda: 'derp',
        getLobbyThread=lambda: lobbythread
    )

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
    monkeypatch.setattr(ladderGamesContainer, 'QSqlQuery', sqlquery)
    return ladder1v1GamesContainerClass(db)
