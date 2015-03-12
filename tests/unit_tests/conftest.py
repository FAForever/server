from unittest import mock
import pytest
from PySide import QtSql

from src.gameconnection import GameConnection
from lobbyserver import FAServerThread


@pytest.fixture()
def sqlquery():
    query = mock.MagicMock()
    query.exec_ = lambda: 0
    query.size = lambda: 0
    query.lastInsertId = lambda: 1
    query.prepare = lambda q: None
    query.addBindValue = lambda v: None
    return query


@pytest.fixture()
def lobbythread():
    return mock.Mock(
        sendJSON=lambda obj: None
    )


@pytest.fixture()
def db(sqlquery):
    db = QtSql.QSqlDatabase()  # mock.MagicMock(spec=QtSql.QSqlDatabase)
    db.exec_ = lambda q: sqlquery
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
