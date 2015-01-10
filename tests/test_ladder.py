from gameModes import ladderGamesContainer, ladder1v1GamesContainerClass

import pytest
import random
from PySide import QtSql
from flexmock import flexmock


sqlquerymock = flexmock(
    exec_=lambda s=None: None,
    size=lambda: 0,
    lastInsertId=lambda: 1,
    prepare=lambda q: None,
    addBindValue=lambda v: None
)

lobbythreadmock = flexmock(
    sendJSON=lambda obj: None
)

@pytest.fixture()
def db():
    return flexmock(QtSql.QSqlDatabase)

@pytest.fixture()
def container(db, monkeypatch):
    monkeypatch.setattr(QtSql, 'QSqlQuery', sqlquerymock)
    return ladder1v1GamesContainerClass(db)


def playerMock(id):
    return flexmock(
        getLogin=lambda: "Player %s" % id,
        setAction=lambda action: None,
        getId=lambda: id,
        setWantGame=lambda bool: None,
        setGame=lambda uid: None,
        getGamePort=lambda: 4242,
        getLeague=lambda: 'derp',
        getLobbyThread=lambda: lobbythreadmock
    )


def test_starts_game_with_map_from_player1(monkeypatch, container):
    def fakeMaps(id):
        if id == 1:
            return [1, 3, 5, 7, 8]
        else:
            return [2, 4, 6, 9]

    def fakeMapName(id):
        return id

    sentJson = {}
    def lobbyThreadMapSpy(json):
        # Python 2 has no nonlocal keyword...
        sentJson['mapname'] = json['mapname']

    player_maps_stub = flexmock()
    monkeypatch.setattr(ladderGamesContainer, 'QSqlQuery', sqlquerymock)
    monkeypatch.setattr(random, 'randint', lambda a, b: 1)

    flexmock(container)
    container.should_receive('getSelectedLadderMaps').replace_with(fakeMaps)
    container.should_receive('getMapName').replace_with(fakeMapName)

    player1, player2 = playerMock(1), playerMock(2)

    lobbythreadmock.should_receive('sendJSON').replace_with(lobbyThreadMapSpy).once()

    container.startGame(player1, player2)

    assert int(sentJson['mapname']) in fakeMaps(1)