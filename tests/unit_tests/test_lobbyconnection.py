import pytest
from unittest import mock
from server import ServerContext, QDataStreamProtocol, GameState, VisibilityState

from server.game_service import GameService
from server.games import Game
from server.lobbyconnection import LobbyConnection
from server.player_service import PlayerService
from server.players import Player


@pytest.fixture()
def test_game_info():
    return {
        'title': 'Test game',
        'gameport': '8000',
        'visibility': VisibilityState.to_string(VisibilityState.PUBLIC),
        'mod': 'faf',
        'mapname': 'scmp_007',
        'password': None,
        'lobby_rating': 1,
        'options': []
    }

@pytest.fixture()
def test_game_info_invalid():
    return {
        'title': 'Title with non ASCI char \xc3',
        'gameport': '8000',
        'visibility': VisibilityState.to_string(VisibilityState.PUBLIC),
        'mod': 'faf',
        'mapname': 'scmp_007',
        'password': None,
        'lobby_rating': 1,
        'options': []
    }

@pytest.fixture
def mock_player():
    return mock.create_autospec(Player(login='Dummy', id=42))

@pytest.fixture
def mock_context(loop):
    return mock.create_autospec(ServerContext(lambda: None, loop))

@pytest.fixture
def mock_players(mock_db_pool):
    return mock.create_autospec(PlayerService(mock_db_pool))

@pytest.fixture
def mock_games(mock_players):
    return mock.create_autospec(GameService(mock_players))

@pytest.fixture
def mock_protocol():
    return mock.create_autospec(QDataStreamProtocol(mock.Mock(), mock.Mock()))

@pytest.fixture
def fa_server_thread(loop, mock_context, mock_protocol, mock_games, mock_players, mock_player, db):
    lc = LobbyConnection(loop,
                         context=mock_context,
                         games=mock_games,
                         players=mock_players,
                         db=db)
    lc.player = mock_player
    lc.protocol = mock_protocol
    return lc


def test_command_game_host_creates_game(fa_server_thread,
                                        mock_games,
                                        test_game_info,
                                        players):
    fa_server_thread.player = players.hosting
    players.hosting.in_game = False
    fa_server_thread.protocol = mock.Mock()
    fa_server_thread.command_game_host(test_game_info)
    expected_call = {
        'game_mode': test_game_info['mod'],
        'name': test_game_info['title'],
        'host': players.hosting,
        'visibility': VisibilityState.to_string(VisibilityState.PUBLIC),
        'password': test_game_info['password'],
        'mapname': test_game_info['mapname'],
    }
    mock_games.create_game\
        .assert_called_with(**expected_call)

def test_command_game_join_calls_join_game(mocker,
                                           fa_server_thread,
                                           game_service,
                                           test_game_info,
                                           players):
    fa_server_thread.game_service = game_service
    mock_protocol = mocker.patch.object(fa_server_thread, 'protocol')
    game = mock.create_autospec(Game(42, game_service))
    game.state = GameState.LOBBY
    game.password = None
    game.game_mode = 'faf'
    game_service.games[42] = game
    fa_server_thread.player = players.hosting
    players.hosting.in_game = False
    test_game_info['uid'] = 42

    fa_server_thread.command_game_join(test_game_info)
    expected_reply = {
        'command': 'game_launch',
        'mod': 'faf',
        'uid': 42,
        'args': ['/numgames {}'.format(players.hosting.numGames)]
    }
    mock_protocol.send_message.assert_called_with(expected_reply)


def test_command_game_host_calls_host_game_invalid_title(fa_server_thread,
                                                         mock_games,
                                                         test_game_info_invalid):
    fa_server_thread.sendJSON = mock.Mock()
    mock_games.create_game = mock.Mock()
    fa_server_thread.command_game_host(test_game_info_invalid)
    assert mock_games.create_game.mock_calls == []
    fa_server_thread.sendJSON.assert_called_once_with(dict(command="notice", style="error", text="Non-ascii characters in game name detected."))


def test_abort(loop, mocker, fa_server_thread):
    proto = mocker.patch.object(fa_server_thread, 'protocol')

    fa_server_thread.abort()

    proto.writer.write_eof.assert_any_call()


def test_ask_session(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.command_ask_session({})
    (response, ), _ = fa_server_thread.sendJSON.call_args
    assert response['command'] == 'welcome'

# Avatar
def test_avatar_upload_user(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.player.admin.return_value = False
    with pytest.raises(KeyError):
        fa_server_thread.command_avatar({'action': 'upload_avatar',
                                         'name': '', 'file': '', 'description': ''})

def test_avatar_list_avatar(mocker, fa_server_thread):
    mock_query = mocker.patch('server.lobbyconnection.QSqlQuery')

    fa_server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 1
    mock_query.return_value.next.side_effect = [True, True, False]
    fa_server_thread.command_avatar({'action': 'list_avatar'})
    (response, ), _ = fa_server_thread.sendJSON.call_args
    assert response['command'] == 'avatar'
    assert len(response['avatarlist']) == 2

# TODO: @sheeo return JSON message on empty avatar list?
def test_avatar_list_avatar_empty(mocker, fa_server_thread):
    mock_query = mocker.patch('server.lobbyconnection.QSqlQuery')

    fa_server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 0
    fa_server_thread.command_avatar({'action': 'list_avatar'})
    assert fa_server_thread.sendJSON.mock_calls == []

def test_avatar_select(mocker, fa_server_thread):
    mock_query = mocker.patch('server.lobbyconnection.QSqlQuery')

    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.command_avatar({'action': 'select', 'avatar': ''})
    assert mock_query.return_value.exec_.call_count == 2

def test_avatar_select_remove(mocker, fa_server_thread):
    mock_query = mocker.patch('server.lobbyconnection.QSqlQuery')

    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.command_avatar({'action': 'select', 'avatar': None})
    assert mock_query.return_value.exec_.call_count == 1

def test_avatar_select_no_avatar(mocker, fa_server_thread):
    mocker.patch('server.lobbyconnection.QSqlQuery')
    with pytest.raises(KeyError):
        fa_server_thread.command_avatar({'action': 'select'})

def test_send_game_list(mocker, fa_server_thread):
    protocol = mocker.patch.object(fa_server_thread, 'protocol')
    games = mocker.patch.object(fa_server_thread, 'game_service')
    game1, game2 = mock.create_autospec(Game(42, mock.Mock())), mock.create_autospec(Game(22, mock.Mock()))
    games.live_games = [game1, game2]

    fa_server_thread.send_game_list()

    protocol.send_messages.assert_any_call([game1.to_dict(), game2.to_dict()])

def test_send_mod_list(mocker, fa_server_thread, mock_games):
    protocol = mocker.patch.object(fa_server_thread, 'protocol')

    fa_server_thread.send_mod_list()

    protocol.send_messages.assert_called_with(mock_games.all_game_modes())

def test_command_admin_closelobby(mocker, fa_server_thread):
    mocker.patch.object(fa_server_thread, 'protocol')
    mocker.patch.object(fa_server_thread, '_logger')
    config = mocker.patch('server.lobbyconnection.config')
    player = mocker.patch.object(fa_server_thread, 'player')
    player.login = 'Sheeo'
    tuna = mock.Mock()
    tuna.id = 55
    fa_server_thread.player_service = {1: player, 55: tuna}

    fa_server_thread.command_admin({
        'command': 'admin',
        'action': 'closelobby',
        'user_id': 55
    })

    tuna.lobby_connection.sendJSON.assert_any_call(dict(
        command='notice',
        style='info',
        text=("Your client was closed by an administrator (Sheeo). "
              "Please refer to our rules for the lobby/game here {rule_link}."
              .format(rule_link=config.RULE_LINK))
    ))

def test_command_admin_closeFA(mocker, fa_server_thread):
    mocker.patch.object(fa_server_thread, 'protocol')
    mocker.patch.object(fa_server_thread, '_logger')
    config = mocker.patch('server.lobbyconnection.config')
    player = mocker.patch.object(fa_server_thread, 'player')
    player.login = 'Sheeo'
    player.id = 42
    tuna = mock.Mock()
    tuna.id = 55
    fa_server_thread.player_service = {42: player, 55: tuna}

    fa_server_thread.command_admin({
        'command': 'admin',
        'action': 'closeFA',
        'user_id': 55
    })

    tuna.lobby_connection.sendJSON.assert_any_call(dict(
        command='notice',
        style='info',
        text=("Your game was closed by an administrator (Sheeo). "
              "Please refer to our rules for the lobby/game here {rule_link}."
              .format(rule_link=config.RULE_LINK))
    ))

