from unittest import mock
from flexmock import flexmock
import pytest
from PySide import QtSql

from src.gameconnection import GameConnection
from lobbyserver import FAServerThread

@pytest.fixture()
def sqlquery():
    return flexmock(
        exec_=lambda s=None: None,
        size=lambda: 0,
        lastInsertId=lambda: 1,
        prepare=lambda q: None,
        addBindValue=lambda v: None
    )

@pytest.fixture()
def lobbythread():
    return flexmock(
        sendJSON=lambda obj: None
    )

@pytest.fixture()
def db():
    db = QtSql.QSqlDatabase() #mock.Mock(spec=QtSql.QSqlDatabase)
    db.isOpen = mock.Mock(return_value=True)
    return db

@pytest.fixture
def game_connection(game, loop, player_service, players, games, transport, monkeypatch, connected_game_socket):
    conn = GameConnection(loop=loop, users=player_service, games=games, db=None, server=None)
    conn.socket = connected_game_socket
    conn.transport = transport
    conn.player = players.hosting
    conn.game = game
    game_connection.lobby = mock.Mock(spec=FAServerThread)
    return conn

@pytest.fixture
def connections(loop, player_service, players, games, transport, connected_game_socket, game_connection):
    def make_connection(player, connectivity):
        conn = GameConnection(loop=loop, users=player_service, games=games, db=None, server=None)
        conn.player = player
        conn.transport = transport
        conn.connectivity_state.set_result(connectivity)
        return conn
    return mock.Mock(
        make_connection=make_connection
    )
