from FaServerThread import FAServerThread, playersOnline
from FaLobbyServer import FALobbyServer
from PySide import QtNetwork

import pytest
import games
import mock


@pytest.fixture()
def test_game_info():
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
    sock = mock.Mock(spec=QtNetwork.QTcpSocket)
    sock.state = mock.Mock(return_value=3)
    sock.isValid = mock.Mock(return_value=True)
    return sock


@pytest.fixture
def mock_lobby_server(db):
    users = playersOnline()
    hyper_container = games.hyperGamesContainerClass(users, db, [])
    return FALobbyServer(users, hyper_container, db, [])

def test_command_game_host_calls_host_game(connected_socket,
                                           mock_lobby_server,
                                           test_game_info):
    server_thread = FAServerThread(connected_socket, mock_lobby_server)
    server_thread.player.getRating = mock.Mock(return_value=mock.Mock(
        getRating=mock.Mock(return_value=mock.Mock(
            getStandardDeviation=lambda: 500
        ))
    ))
    server_thread.command_game_host(test_game_info)
