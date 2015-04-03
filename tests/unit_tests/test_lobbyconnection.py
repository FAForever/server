from PySide import QtNetwork
import json
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
        'options': []
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
        'options': []
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


@pytest.fixture
def fa_server_thread(connected_socket, mock_lobby_server):
    return LobbyConnection(connected_socket, mock_lobby_server)


def test_command_game_host_calls_host_game(fa_server_thread,
                                           mock_lobby_server,
                                           test_game_info,
                                           players):
    fa_server_thread.player = players.hosting
    mock_lobby_server.games.create_game = mock.Mock()
    fa_server_thread.command_game_host(test_game_info)
    mock_lobby_server.games.create_game\
        .assert_called_with(test_game_info['access'],
                            test_game_info['mod'],
                            fa_server_thread.player,
                            test_game_info['title'],
                            test_game_info['gameport'],
                            test_game_info['mapname'],
                            test_game_info['version'])


def test_command_game_host_calls_host_game_invalid_title(fa_server_thread,
                                                         mock_lobby_server,
                                                         test_game_info_invalid):
    fa_server_thread.sendJSON = mock.Mock()
    mock_lobby_server.games.create_game = mock.Mock()
    fa_server_thread.command_game_host(test_game_info_invalid)
    assert mock_lobby_server.games.create_game.mock_calls == []
    fa_server_thread.sendJSON.assert_called_once_with(dict(command="notice", style="error", text="Non-ascii characters in game name detected."))

# ModVault
@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.Config')
def test_mod_vault_start(mock_config, mock_query, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 1
    mock_query.return_value.next.side_effect = [True, False]
    fa_server_thread.command_modvault({'type': 'start'})
    fa_server_thread.sendJSON.assert_called_once()
    assert fa_server_thread.sendJSON.call_count == 1
    (response, ), _ = fa_server_thread.sendJSON.call_args
    assert response['command'] == 'modvault_info'

@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.Config')
def test_mod_vault_like(mock_config, mock_query, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 1
    fa_server_thread.command_modvault({'type': 'like',
                                    'uid': 'a valid one'})
    assert fa_server_thread.sendJSON.call_count == 1
    (response, ), _ = fa_server_thread.sendJSON.call_args
    assert response['command'] == 'modvault_info'

@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.Config')
def test_mod_vault_like_invalid_uid(mock_config, mock_query, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 0
    fa_server_thread.command_modvault({'type': 'like',
                                    'uid': 'something_invalid'})
    # call, method:attributes, attribute_index
    assert fa_server_thread.sendJSON.mock_calls == []

@mock.patch('src.lobbyconnection.QSqlQuery')
def test_mod_vault_download(mock_query, fa_server_thread):
    fa_server_thread.command_modvault({'type': 'download',
                                    'uid': None})
    mock_query.return_value.prepare.assert_called_with("UPDATE `table_mod` SET downloads=downloads+1 WHERE uid = ?")


def test_mod_vault_addcomment(fa_server_thread):
    with pytest.raises(NotImplementedError):
        fa_server_thread.command_modvault({'type': 'addcomment'})


def test_mod_vault_invalid_type(fa_server_thread):
    with pytest.raises(ValueError):
        fa_server_thread.command_modvault({'type': 'DragonfireNegativeTest'})


def test_mod_vault_no_type(fa_server_thread):
    with pytest.raises(KeyError):
        fa_server_thread.command_modvault({'invalidKey': None})

# Social
def test_social_invalid(fa_server_thread):
    with pytest.raises(KeyError):
        fa_server_thread.command_social({'invalidKey': None})

def test_social_teaminvite(fa_server_thread):
    fa_server_thread.parent.listUsers.findByName = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.player.getLogin.return_value = "Team Leader"
    fa_server_thread.command_social({'teaminvite': 'Dragonfire'})
    fa_server_thread.parent.listUsers.findByName.assert_called_with('Dragonfire')
    fa_server_thread.parent.listUsers.findByName.return_value.lobbyThread.sendJSON \
        .assert_called_with(dict(command="team", action="teaminvitation", who="Team Leader"))


# TODO: check in ingetration tests db state
def test_social_friends(fa_server_thread):
    fa_server_thread.parent.listUsers.findByName = mock.Mock()
    assert fa_server_thread.friendList == []
    friends = {'Sheeo', 'Dragonfire', 'Spooky'}
    fa_server_thread.command_social({'friends': friends})
    assert fa_server_thread.friendList == friends


# TODO: check in ingetration tests db state
def test_social_foes(fa_server_thread):
    fa_server_thread.parent.listUsers.findByName = mock.Mock()
    assert fa_server_thread.foeList == []
    foes = {'Cheater', 'Haxxor', 'Boom1234'}
    fa_server_thread.command_social({'foes': foes})
    assert fa_server_thread.foeList == foes


# Ask Session
# TODO: @sheeo add special cases with Timer
def test_ask_session(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.command_ask_session({})
    (response, ), _ = fa_server_thread.sendJSON.call_args
    assert response['command'] == 'welcome'

# Avatar
@mock.patch('zlib.decompress')
@mock.patch('src.lobbyconnection.Config')
@mock.patch('src.lobbyconnection.QFile')
@mock.patch('src.lobbyconnection.QSqlQuery')
def test_avatar_upload_admin(mock_query, mock_file, mock_config, mock_zlib, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.player.admin.return_value = True
    fa_server_thread.command_avatar({'action': 'upload_avatar',
                                     'name': '', 'file': '', 'description': ''})
    fa_server_thread.sendJSON.assert_called_once_with(
        dict(command="notice", style="info", text="Avatar uploaded."))


def test_avatar_upload_admin_invalid_file(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.player.admin.return_value = True
    with pytest.raises(KeyError):
        fa_server_thread.command_avatar({'action': 'upload_avatar',
                                         'name': '', 'file': '', 'description': ''})

@mock.patch('zlib.decompress')
@mock.patch('src.lobbyconnection.Config')
@mock.patch('src.lobbyconnection.QFile')
@mock.patch('src.lobbyconnection.QSqlQuery')
def test_avatar_upload_admin_db_error(mock_query, mock_file, mock_config, mock_zlib, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.player.admin.return_value = True
    mock_query.return_value.exec_.return_value = False
    fa_server_thread.command_avatar({'action': 'upload_avatar',
                                     'name': '', 'file': '', 'description': ''})
    fa_server_thread.sendJSON.assert_called_once_with(
        dict(command="notice", style="error", text="Avatar not correctly uploaded."))

def test_avatar_upload_user(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.player.admin.return_value = False
    with pytest.raises(KeyError):
        fa_server_thread.command_avatar({'action': 'upload_avatar',
                                         'name': '', 'file': '', 'description': ''})

@mock.patch('src.lobbyconnection.QSqlQuery')
def test_avatar_list_avatar(mock_query, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 1
    mock_query.return_value.next.side_effect = [True, True, False]
    fa_server_thread.command_avatar({'action': 'list_avatar'})
    (response, ), _ = fa_server_thread.sendJSON.call_args
    assert response['command'] == 'avatar'
    assert len(response['avatarlist']) == 2

# TODO: @sheeo return JSON message on empty avatar list?
@mock.patch('src.lobbyconnection.QSqlQuery')
def test_avatar_list_avatar_empty(mock_query, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    mock_query.return_value.size.return_value = 0
    fa_server_thread.command_avatar({'action': 'list_avatar'})
    assert fa_server_thread.sendJSON.mock_calls == []

@mock.patch('src.lobbyconnection.QSqlQuery')
def test_avatar_select(mock_query, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.command_avatar({'action': 'select', 'avatar': ''})
    assert mock_query.return_value.exec_.call_count == 2

@mock.patch('src.lobbyconnection.QSqlQuery')
def test_avatar_select_remove(mock_query, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.command_avatar({'action': 'select', 'avatar': None})
    assert mock_query.return_value.exec_.call_count == 1

@mock.patch('src.lobbyconnection.QSqlQuery')
def test_avatar_select_no_avatar(mock_query, fa_server_thread):
    with pytest.raises(KeyError):
        fa_server_thread.command_avatar({'action': 'select'})


def test_handle_action_ping(fa_server_thread):
    fa_server_thread.sendReply = mock.Mock()
    fa_server_thread.handleAction('PING', mock.Mock())
    fa_server_thread.sendReply.assert_called_once_with('PONG')


def test_handle_action_pong(fa_server_thread):
    assert fa_server_thread.ponged is False
    fa_server_thread.handleAction('PONG', mock.Mock())
    assert fa_server_thread.ponged is True


def test_handle_action_faclosed(fa_server_thread):
    fa_server_thread.player = mock.Mock()
    fa_server_thread.handleAction('FA_CLOSED', mock.Mock())
    fa_server_thread.player.setAction.assert_called_once_with('NOTHING')
    fa_server_thread.player.gameThread.abort.assert_called_once_with()


def test_handle_action_possible_json_commannd(fa_server_thread):
    fa_server_thread.receiveJSON = mock.Mock()
    stream = mock.Mock()
    fa_server_thread.handleAction('CrazyThing', stream)
    fa_server_thread.receiveJSON.assert_called_once_with(
        'CrazyThing', stream)


def test_handle_action_invalidData(fa_server_thread):
    fa_server_thread.log = mock.Mock()
    fa_server_thread.handleAction(None, None)
    assert fa_server_thread.log.exception.call_count == 1

# handle action - Create Account
# TODO: for @ckitching or if pr #23 is merged

# handle action - UPLOAD_MOD
# TODO: move to web api
# TODO: check if params are valid
@mock.patch('src.lobbyconnection.Config')
@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.QFile')
@mock.patch('src.lobbyconnection.zipfile')
def test_handle_action_upload_mod(mock_zipfile, mock_qfile, mock_query, mock_config, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()

    stream = mock.Mock()
    zipMap = mock.MagicMock()
    infos = json.dumps({'name': '', 'uid': '', 'description': '',
                        'author': '', 'ui_only': '', 'version': '',
                        'small': '', 'big': ''})
    stream.readQString.side_effect = ['', '', zipMap, infos, 0, mock.Mock()]

    # fake no db entry exists
    mock_query.return_value.size.return_value = 0

    fa_server_thread.handleAction('UPLOAD_MOD', stream)
    fa_server_thread.sendJSON.assert_called_once_with(
        dict(command="notice", style="info", text="Mod correctly uploaded."))

@mock.patch('src.lobbyconnection.Config')
@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.QFile')
@mock.patch('src.lobbyconnection.zipfile')
def test_handle_action_upload_mod_invalid_zip(mock_zipfile, mock_qfile, mock_query, mock_config, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()

    stream = mock.Mock()
    zipMap = mock.MagicMock()
    infos = json.dumps({'name': '', 'uid': '', 'description': '',
                        'author': '', 'ui_only': '', 'version': '',
                        'small': '', 'big': ''})
    stream.readQString.side_effect = ['', '', zipMap, infos, 0, mock.Mock()]

    # fake no db entry exists
    mock_query.return_value.size.return_value = 0

    # is invalid zip
    mock_zipfile.is_zipfile.return_value = False

    fa_server_thread.handleAction('UPLOAD_MOD', stream)
    (response, ), _ = fa_server_thread.sendJSON.call_args
    assert response['command'] == 'notice'
    assert response['style'] == 'error'

@mock.patch('src.lobbyconnection.Config')
@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.QFile')
@mock.patch('src.lobbyconnection.zipfile')
def test_handle_action_upload_mod_exists(mock_zipfile, mock_qfile, mock_query, mock_config, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()

    stream = mock.Mock()
    zipMap = mock.MagicMock()
    infos = json.dumps({'name': '', 'uid': '', 'description': '',
                        'author': '', 'ui_only': '', 'version': '',
                        'small': '', 'big': ''})
    stream.readQString.side_effect = ['', '', zipMap, infos, 0, mock.Mock()]

    # Mod already exists
    mock_query.return_value.size.return_value = 1

    fa_server_thread.handleAction('UPLOAD_MOD', stream)
    (response, ), _ = fa_server_thread.sendJSON.call_args
    assert response['command'] == 'notice'
    assert response['style'] == 'error'


def test_handle_action_upload_mod_invalid_messages(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()

    zipMap = mock.MagicMock()
    infos = {'name': '', 'uid': '', 'description': '',
             'author': '', 'ui_only': '', 'version': '',
             'small': '', 'big': ''}

    error_messages = {'name': 'No mod name provided.',
                      'uid': 'No uid provided.',
                      'description': 'No description provided.',
                      'author': 'No author provided.',
                      'ui_only': 'No mod type provided.',
                      'version': 'No mod version provided.',
                      'big': 'No big provided.',
                      'small': 'No small provided.'}

    for key in infos:
        stream = mock.Mock()
        invalid_message = infos.copy()
        del invalid_message[key]
        stream.readQString.side_effect = ['', '', zipMap, json.dumps(invalid_message), 0, mock.Mock()]

        fa_server_thread.handleAction('UPLOAD_MOD', stream)
        (response, ), _ = fa_server_thread.sendJSON.call_args
        assert response['command'] == 'notice'
        assert response['style'] == 'error'
        assert response['text'] == error_messages[key]

# handle action - UPLOAD_MAP
# TODO: move to web api
# TODO: check if params are valid
@mock.patch('src.lobbyconnection.Config')
@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.QFile')
@mock.patch('src.lobbyconnection.zipfile')
def test_handle_action_upload_map(mock_zipfile, mock_qfile, mock_query, mock_config, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()

    stream = mock.Mock()
    zipMap = mock.MagicMock()
    infos = json.dumps({'name': '', 'description': '', 'max_players': '',
                        'map_type': '', 'battle_type': '', 'map_size': {'0': '', '1': ''},
                        'version': ''})
    stream.readQString.side_effect = ['', '', zipMap, infos, 0, mock.Mock()]

    # fake no db entry exists
    mock_query.return_value.size.return_value = 0


    fa_server_thread.handleAction('UPLOAD_MAP', stream)
    fa_server_thread.sendJSON.assert_called_once_with(
        dict(command="notice", style="info", text="Map correctly uploaded."))

@mock.patch('src.lobbyconnection.Config')
@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.QFile')
@mock.patch('src.lobbyconnection.zipfile')
def test_handle_action_upload_map_invalid_zip(mock_zipfile, mock_qfile, mock_query, mock_config, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()

    stream = mock.Mock()
    zipMap = mock.MagicMock()
    infos = json.dumps({'name': '', 'description': '', 'max_players': '',
                        'map_type': '', 'battle_type': '', 'map_size': {'0': '', '1': ''},
                        'version': ''})
    stream.readQString.side_effect = ['', '', zipMap, infos, 0, mock.Mock()]

    # fake no db entry exists
    mock_query.return_value.size.return_value = 0

    # is invalid zip
    mock_zipfile.is_zipfile.return_value = False

    fa_server_thread.handleAction('UPLOAD_MAP', stream)
    fa_server_thread.sendJSON.assert_called_once_with(
        dict(command="notice", style="error", text="Cannot unzip map. Upload error ?"))

@mock.patch('src.lobbyconnection.Config')
@mock.patch('src.lobbyconnection.QSqlQuery')
@mock.patch('src.lobbyconnection.QFile')
@mock.patch('src.lobbyconnection.zipfile')
def test_handle_action_upload_map_exists(mock_zipfile, mock_qfile, mock_query, mock_config, fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()

    stream = mock.Mock()
    zipMap = mock.MagicMock()
    infos = json.dumps({'name': '', 'description': '', 'max_players': '',
                        'map_type': '', 'battle_type': '', 'map_size': {'0': '', '1': ''},
                        'version': ''})
    stream.readQString.side_effect = ['', '', zipMap, infos, 0, mock.Mock()]

    # map allready exists
    mock_query.return_value.size.return_value = 1

    fa_server_thread.handleAction('UPLOAD_MAP', stream)
    (response, ), _ = fa_server_thread.sendJSON.call_args
    assert response['command'] == 'notice'
    assert response['style'] == 'error'


def test_handle_action_upload_map_invalid_messages(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()

    zipMap = mock.MagicMock()
    infos = {'name': '', 'description': '', 'max_players': '',
             'map_type': '', 'battle_type': '', 'map_size': {'0': '', '1': ''},
             'version': ''}

    error_messages = {'name': 'No map name provided.',
                      'description': 'No map description provided.',
                      'max_players': 'No max players provided.',
                      'map_type': 'No map type provided.',
                      'battle_type': 'No battle type provided.',
                      'map_size': 'No map size provided.',
                      'version': 'No version provided.'}

    for key in infos:
        stream = mock.Mock()
        invalid_message = infos.copy()
        del invalid_message[key]
        stream.readQString.side_effect = ['', '', zipMap, json.dumps(invalid_message), 0, mock.Mock()]

        fa_server_thread.handleAction('UPLOAD_MAP', stream)
        (response, ), _ = fa_server_thread.sendJSON.call_args
        assert response['command'] == 'notice'
        assert response['style'] == 'error'
        assert response['text'] == error_messages[key]


def test_fa_state(fa_server_thread):
    fa_server_thread.player = mock.Mock()
    fa_server_thread.player.getAction.return_value = 'NOTHING'
    message = {'state': 'on'}
    assert fa_server_thread.player.setAction.call_count == 0
    fa_server_thread.command_fa_state(message)
    fa_server_thread.player.setAction.assert_called_once_with('FA_LAUNCHED')
    assert fa_server_thread.player.setAction.call_count == 1
    # if called again action is not set
    fa_server_thread.player.getAction.return_value = 'FA_LAUNCHED'
    fa_server_thread.command_fa_state(message)
    assert fa_server_thread.player.setAction.call_count == 1
    # reset state
    fa_server_thread.command_fa_state({'state': 'off'})
    fa_server_thread.player.setAction.assert_called_with('NOTHING')
    assert fa_server_thread.player.setAction.call_count == 2
    # test if launching is working after reset
    fa_server_thread.player.getAction.return_value = 'NOTHING'
    fa_server_thread.command_fa_state(message)
    fa_server_thread.player.setAction.assert_called_with('FA_LAUNCHED')
    assert fa_server_thread.player.setAction.call_count == 3


def test_fa_state_reset(fa_server_thread):
    fa_server_thread.player = mock.Mock()
    reset_values = {None, '', 'ON', 'off'}
    for val in reset_values:
        fa_server_thread.command_fa_state({'state': val})
        fa_server_thread.player.setAction.assert_called_with('NOTHING')


def test_fa_state_invalid(fa_server_thread):
    with pytest.raises(KeyError):
        fa_server_thread.command_ladder_maps({})
        fa_server_thread.command_ladder_maps(None)


def test_ladder_maps(fa_server_thread):
    maps = [42, -1, 2341, -123, 123]
    fa_server_thread.command_ladder_maps({'maps' : maps})
    assert fa_server_thread.ladderMapList == maps
    # reset map selection
    maps = []
    fa_server_thread.command_ladder_maps({'maps' : maps})
    assert fa_server_thread.ladderMapList == maps


def test_ladder_maps_invalid_message(fa_server_thread):
    with pytest.raises(KeyError):
        fa_server_thread.command_ladder_maps({})
        fa_server_thread.command_ladder_maps(None)


# TODO: missing JSON send for me as player who left
def test_quit_team_as_member(fa_server_thread):
    fa_server_thread.lobbyThread = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.parent = mock.Mock()
    all_members = ['PlayerA', 'me', 'PlayerB']
    new_members = ['PlayerA', 'PlayerB']
    leader = 'PlayerB'
    fa_server_thread.parent.teams.getAllMembers.side_effect = [all_members, new_members]
    fa_server_thread.parent.teams.getSquadLeader.return_value = leader
    player_sender = mock.Mock()
    fa_server_thread.parent.listUsers.findByName.return_value = player_sender

    fa_server_thread.command_quit_team(None)
    # I was removed from team
    assert fa_server_thread.parent.teams.removeFromSquad.call_count == 1
    # notify players
    player_sender.lobbyThread.sendJSON.assert_called_with(
        dict(command="team_info", leader=leader, members=new_members))
    assert player_sender.lobbyThread.sendJSON.call_count == 2


def test_quit_team_as_member_to_small_team(fa_server_thread):
    fa_server_thread.lobbyThread = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.parent = mock.Mock()
    all_members = ['PlayerA', 'me']
    new_members = ['PlayerA']
    leader = 'PlayerB'
    fa_server_thread.parent.teams.getAllMembers.side_effect = [all_members, new_members]
    fa_server_thread.parent.teams.getSquadLeader.return_value = leader
    player_sender = mock.Mock()
    fa_server_thread.parent.listUsers.findByName.return_value = player_sender

    fa_server_thread.command_quit_team(None)
    # I was removed from team
    assert fa_server_thread.parent.teams.disbandSquad.call_count == 1
    # notify NOT players
    assert player_sender.lobbyThread.sendJSON.call_count == 0


def test_quit_team_as_leader(fa_server_thread):
    fa_server_thread.lobbyThread = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.parent = mock.Mock()
    all_members = ['PlayerA', 'me', 'PlayerB']
    leader = 'me'
    fa_server_thread.player.getLogin.return_value = 'me'
    fa_server_thread.parent.teams.getAllMembers.return_value = all_members
    fa_server_thread.parent.teams.getSquadLeader.return_value = leader
    player_sender = mock.Mock()
    fa_server_thread.parent.listUsers.findByName.return_value = player_sender

    fa_server_thread.command_quit_team(None)
    # Team was removed
    assert fa_server_thread.parent.teams.disbandSquad.call_count == 1
    # notify players
    player_sender.lobbyThread.sendJSON.assert_called_with(
        dict(command="team_info", leader="", members=[]))
    assert player_sender.lobbyThread.sendJSON.call_count == 3


def test_quit_team_without_in_a_team(fa_server_thread):
    fa_server_thread.parent = mock.Mock()
    fa_server_thread.player = mock.Mock()
    fa_server_thread.parent.teams.getSquadLeader.return_value = False
    fa_server_thread.command_quit_team(None)
    # no notifications
    assert fa_server_thread.parent.listUsers.findByName.lobbyThread.sendJSON.call_count == 0


# TODO: check if squad invited him? over crypto?
def test_accept_team_proposal(fa_server_thread):
    fa_server_thread.parent = mock.Mock()
    fa_server_thread.player = mock.Mock()
    player_sender = mock.Mock()
    members = ['PlayerA', 'CoolLeaderName']
    new_members = ['PlayerA', 'me', 'CoolLeaderName']
    # possible to add us to the squad
    fa_server_thread.parent.teams.getAllMembers.side_effect = [members, new_members]
    fa_server_thread.parent.teams.addInSquad.return_value = True
    fa_server_thread.parent.listUsers.findByName.return_value = player_sender

    fa_server_thread.command_accept_team_proposal({'leader': 'CoolLeaderName'})
    # check if all members get an notification
    player_sender.lobbyThread.sendJSON.assert_called_with(
        dict(command="team_info", leader="CoolLeaderName", members=new_members))
    assert player_sender.lobbyThread.sendJSON.call_count == 3


def test_accept_team_is_full(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.parent = mock.Mock()
    members = ['TeamIs', 'FullIf', 'FourOr', 'MorePlayers']
    fa_server_thread.parent.teams.getAllMembers.return_value = members
    fa_server_thread.command_accept_team_proposal({'leader': 'MockThisAway'})
    fa_server_thread.sendJSON.assert_called_once_with(
        dict(command="notice", style="info", text="Sorry, the team is full."))


def test_accept_team_your_have_allready_one_team(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.parent = mock.Mock()
    fa_server_thread.player = mock.Mock()
    members = ['PlayerA', 'CoolLeaderName']
    new_members = ['PlayerA', 'me', 'CoolLeaderName']
    # possible to add us to the squad
    fa_server_thread.parent.teams.getAllMembers.side_effect = [members, new_members]
    # You are allready in a squad
    fa_server_thread.parent.teams.addInSquad.return_value = False

    fa_server_thread.command_accept_team_proposal({'leader': 'MockThisAway'})
    fa_server_thread.sendJSON.assert_called_once_with(
        dict(command="notice", style="info", text="Sorry, you cannot join the squad."))


def test_accept_team_no_valid_leader(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.parent = mock.Mock()

    # Leader is not in squad
    fa_server_thread.parent.teams.isInSquad.return_value = False

    fa_server_thread.command_accept_team_proposal({'leader': 'MockThisAway'})
    fa_server_thread.sendJSON.assert_called_once_with(
        dict(command="notice", style="info", text="Leader is not in a squad."))


def test_accept_team_given_leader_is_squad_but_no_leader(fa_server_thread):
    fa_server_thread.sendJSON = mock.Mock()
    fa_server_thread.parent = mock.Mock()

    # Leader is not in squad
    fa_server_thread.parent.teams.isLeader.return_value = False

    fa_server_thread.command_accept_team_proposal({'leader': 'MockThisAway'})
    fa_server_thread.sendJSON.assert_called_once_with(
        dict(command="notice", style="info", text="Squad not found. Wrong Loeader."))


def test_accept_team_proposal_invalid_message(fa_server_thread):
    with pytest.raises(KeyError):
        fa_server_thread.command_accept_team_proposal({})
        fa_server_thread.command_accept_team_proposal(None)
