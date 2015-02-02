import pytest
import mock

from PySide.QtNetwork import QTcpSocket
from PySide.QtCore import QObject


from GameConnection import GameConnection
from games import Game
from players import playersOnline, player as Player

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
def game(players):
    game = mock.MagicMock(spec=Game(1))
    game.hostPlayer = players.hosting
    return game

def player(login, port, action):
    p = mock.Mock(spec=Player)
    p.getGamePort.return_value = port
    p.getAction = mock.Mock(return_value=action)
    p.getLogin = mock.Mock(return_value=login)
    return p

@pytest.fixture
def players():
    return mock.Mock(
        hosting=player('Paula_Bean', 6112, "HOST"),
        peer=player('That_Guy', 6112, "JOIN"),
        joining=player('James_Kirk', 6112, "JOIN")
    )

@pytest.fixture
def player_service(players):
    p = mock.Mock(spec=playersOnline())
    p.findByIp = mock.Mock(return_value=players.hosting)
    return p

@pytest.fixture
def games():
    return mock.Mock()

@pytest.fixture
def game_connection(game, player_service, players, games):
    conn = GameConnection(users=player_service, games=games)
    conn.player = players.hosting
    conn.game = game
    return conn


def test_accepts_valid_socket(game_connection, connected_game_socket):
    assert game_connection.accept(connected_game_socket) is True

def test_handle_action_ConnectedToHost(game, game_connection, players):
    game_connection.player = players.joining
    game_connection.handle_action('ConnectedToHost', [])
    game.add_connection.assert_called_once_with(players.joining, players.hosting)

def test_handle_action_Connected(game, game_connection, players):
    game_connection.player = players.joining
    game_connection.handle_action('Connected', [players.peer])
    game.add_connection.assert_called_once_with(players.joining, players.peer)

def test_handle_action_Connected_no_raise(game_connection, players):
    game_connection.player = players.joining
    game_connection.handle_action('Connected', [])
    # Shouldn't raise an exception

def test_handle_action_Connected_no_raise2(game_connection, players):
    game_connection.player = players.joining
    game_connection.handle_action('Connected', ['garbage', 'garbage2'])
    # Shouldn't raise an exception

def test_handle_action_PlayerOption(game, game_connection):
    game_connection.handle_action('PlayerOption', [1, 'Color', 2])
    game.setPlayerOption.assert_called_once_with(1, 'Color', 2)


def test_handle_action_malformed_PlayerOption_no_raise(game_connection):
    game_connection.handle_action('PlayerOption', [1, 'Sheeo', 'Color', 2])
    # Shouldn't raise an exception


def test_handle_action_GameOption(game, game_connection):
    game_connection.handle_action('PlayerOption', [1, 'Color', 2])
    game.setPlayerOption.assert_called_once_with(1, 'Color', 2)

