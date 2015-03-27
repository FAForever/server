from PySide import QtNetwork
import pytest
import mock

from src.games_service import GamesService
from src.lobbyconnection import LobbyConnection, PlayersOnline
from src.FaLobbyServer import FALobbyServer


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

@pytest.fixture()
def test_game_info_invalid():
    return {
        'title': 'Tittle with non ASCI char \xc3',
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
    users = PlayersOnline()
    hyper_container = GamesService(users, db)
    return FALobbyServer(users, hyper_container, db)

def test_command_game_host_calls_host_game(connected_socket,
                                           mock_lobby_server,
                                           test_game_info):
    server_thread = LobbyConnection(connected_socket, mock_lobby_server)
    server_thread.command_game_host(test_game_info)
    # TODO: check outcome?

def test_command_game_host_calls_host_game_invalid_title(connected_socket,
                                           mock_lobby_server,
                                           test_game_info_invalid):
    server_thread = LobbyConnection(connected_socket, mock_lobby_server)
    server_thread.command_game_host(test_game_info_invalid)
    # TODO: outcome should be Non-ascii characters in game name detected.