from FaServerThread import *
from FaLobbyServer import FALobbyServer
from PySide import QtNetwork

import pytest
import gameModes
import mock


@pytest.fixture()
def test_game():
    return {
        'title': 'Test game',
        'gameport': '8000',
        'access': 'public',
        'mod': 'faf',
        'version': None,
        'mapname': 'scmp_007',
        'password': None,
        'lobby_rating': 1,
        'options':  []
    }


@pytest.fixture(scope='function')
def connected_socket():
    sock = QtNetwork.QTcpSocket()
    sock.state = mock.Mock(return_value=3)
    sock.isValid = mock.Mock(return_value=True)
    return sock


@pytest.fixture
def mock_lobby_server(db):
    users = playersOnline()
    hyper_container = gameModes.hyperGamesContainerClass(users, db, [])
    return FALobbyServer(users, hyper_container, db, [])


def test_command_game_host_calls_host_game(connected_socket, mock_lobby_server, test_game):
    server_thread = FAServerThread(connected_socket, mock_lobby_server)
    server_thread.player.getRating = mock.Mock(return_value=mock.Mock(
        getRating=mock.Mock(return_value=mock.Mock(
            getStandardDeviation=lambda: 500
        ))
    ))
    server_thread.command_game_host(test_game)
