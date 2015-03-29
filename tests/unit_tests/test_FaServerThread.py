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
    mock_lobby_server.games.create_game = mock.Mock()
    server_thread = LobbyConnection(connected_socket, mock_lobby_server)
    server_thread.command_game_host(test_game_info)
    mock_lobby_server.games.create_game\
        .assert_called_with(test_game_info['access'],
                            test_game_info['mod'],
                            server_thread.player,
                            test_game_info['title'],
                            test_game_info['gameport'],
                            test_game_info['mapname'],
                            test_game_info['version'])


def test_command_game_host_calls_host_game_invalid_title(connected_socket,
                                           mock_lobby_server,
                                           test_game_info_invalid):
    server_thread = LobbyConnection(connected_socket, mock_lobby_server)
    server_thread.sendJSON = mock.Mock()
    mock_lobby_server.games.create_game = mock.Mock()
    server_thread.command_game_host(test_game_info_invalid)
    assert mock_lobby_server.games.create_game.mock_calls == []
    server_thread.sendJSON.assert_called_with(dict(command="notice", style="error", text="Non-ascii characters in game name detected."))

# ModVault

# TODO: find a better way
OneTimeTrue = False
def one_time_true():
    global OneTimeTrue
    if OneTimeTrue:
        return False
    OneTimeTrue = True
    return True

@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.Config')
def test_mod_vault_start(mock_config, mock_query, connected_socket, mock_lobby_server):
    server_thread = LobbyConnection(connected_socket, mock_lobby_server)
    server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 1
    mock_query.return_value.next = one_time_true
    server_thread.command_modvault({'type': 'start'})
    server_thread.sendJSON.assert_called_once()
    # call, method:attributes, attribute_index
    assert server_thread.sendJSON.mock_calls[0][1][0]['command'] == 'modvault_info'

@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.Config')
def test_mod_vault_like(mock_config, mock_query, connected_socket, mock_lobby_server):
    server_thread = LobbyConnection(connected_socket, mock_lobby_server)
    server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 1
    server_thread.command_modvault({'type': 'like',
                                    'uid': 'a valid one'})
    # call, method:attributes, attribute_index
    assert server_thread.sendJSON.mock_calls[0][1][0]['command'] == 'modvault_info'

@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.Config')
def test_mod_vault_like_invalid_uid(mock_config, mock_query, connected_socket, mock_lobby_server):
    server_thread = LobbyConnection(connected_socket, mock_lobby_server)
    server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 0
    server_thread.command_modvault({'type': 'like',
                                    'uid': 'something_invalid'})
    # call, method:attributes, attribute_index
    assert server_thread.sendJSON.mock_calls == []

# def test_mod_vault_download(connected_socket,
#                         mock_lobby_server):
#     server_thread = LobbyConnection(connected_socket, mock_lobby_server)
#     server_thread.command_modvault({'type': 'download',
#                                     'uid': None})
#     server_thread.query = mock.Mock()
#     server_thread.query.addBindValue.assert_called_with(None)

# def test_mod_vault_addcomment(connected_socket,
#                               mock_lobby_server):
#     server_thread = LobbyConnection(connected_socket, mock_lobby_server)
#     server_thread.command_modvault({'type': 'addcomment'})
#
# def test_mod_vault_invalid_type(connected_socket,
#                                 mock_lobby_server):
#     server_thread = LobbyConnection(connected_socket, mock_lobby_server)
#     server_thread.command_modvault({'type': 'DragonfireNegativeTest'})

# def test_mod_vault_no_type(connected_socket,
#                            mock_lobby_server):
#     server_thread = LobbyConnection(connected_socket, mock_lobby_server)
#     server_thread.command_modvault({'invalidKey': None})
