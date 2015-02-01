import pytest
import mock
import pytestqt

from PySide.QtNetwork import QTcpSocket


from GameConnection import GameConnection
from games import Game
from players import playersOnline

import logging
logging.getLogger("GameConnection").addHandler(logging.StreamHandler())
logging.getLogger("GameConnection").setLevel(logging.DEBUG)

@pytest.fixture
def connected_game_socket():
    game_socket = mock.Mock(spec=QTcpSocket)
    game_socket.state = mock.Mock(return_value=QTcpSocket.ConnectedState)
    game_socket.isValid = mock.Mock(return_value=True)
    return game_socket

@pytest.fixture
def game():
    return mock.Mock(spec=Game(1))

@pytest.fixture
def player():
    p = mock.Mock()
    p.getGamePort.return_value = 6112
    p.getAction = mock.Mock(return_value="HOST")
    return p

@pytest.fixture
def players(player):
    p = mock.Mock(spec=playersOnline())
    p.findByIp = mock.Mock(return_value=player)
    return p

@pytest.fixture
def game_connection(game, players, player):
    conn = GameConnection(users=players)
    conn.player = player
    conn.game = game
    return conn


def test_accepts_valid_socket(game_connection, connected_game_socket):
    assert game_connection.accept(connected_game_socket) is True


def test_handleAction_PlayerOption(game, game_connection):
    game_connection.handleAction('PlayerOption', [1, 'Color', 2])
    game.setPlayerOption.assert_called_once_with(1, 'Color', 2)


def test_handleAction_GameOption(game, game_connection):
    game_connection.handleAction('PlayerOption', [1, 'Color', 2])
    game.setPlayerOption.assert_called_once_with(1, 'Color', 2)

