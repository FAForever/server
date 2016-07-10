import asyncio
from unittest.mock import Mock

import pytest
from unittest import mock
from server import ServerContext, GameState, VisibilityState, GameStatsService
from server.connectivity import Connectivity
from server.protocol import QDataStreamProtocol
from server.game_service import GameService
from server.games import Game
from server.lobbyconnection import LobbyConnection
from server.player_service import PlayerService
from server.players import Player
from tests import CoroMock

import server.db as db

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
def mock_games(mock_players, game_stats_service):
    return mock.create_autospec(GameService(mock_players, game_stats_service))

@pytest.fixture
def mock_protocol():
    return mock.create_autospec(QDataStreamProtocol(mock.Mock(), mock.Mock()))

@pytest.fixture
def lobbyconnection(loop, mock_context, mock_protocol, mock_games, mock_players, mock_player):
    lc = LobbyConnection(loop,
                         context=mock_context,
                         games=mock_games,
                         players=mock_players)
    lc.player = mock_player
    lc.connectivity = mock.create_autospec(Connectivity)
    lc.protocol = mock_protocol
    return lc


def test_command_game_host_creates_game(lobbyconnection,
                                        mock_games,
                                        test_game_info,
                                        players):
    lobbyconnection.player = players.hosting
    players.hosting.in_game = False
    lobbyconnection.protocol = mock.Mock()
    lobbyconnection.command_game_host(test_game_info)
    expected_call = {
        'game_mode': test_game_info['mod'],
        'name': test_game_info['title'],
        'host': players.hosting,
        'visibility': VisibilityState.PUBLIC,
        'password': test_game_info['password'],
        'mapname': test_game_info['mapname'],
    }
    mock_games.create_game\
        .assert_called_with(**expected_call)


def test_command_game_join_calls_join_game(mocker,
                                           lobbyconnection,
                                           game_service,
                                           test_game_info,
                                           players,
                                           game_stats_service):
    lobbyconnection.game_service = game_service
    mock_protocol = mocker.patch.object(lobbyconnection, 'protocol')
    game = mock.create_autospec(Game(42, game_service, game_stats_service))
    game.state = GameState.LOBBY
    game.password = None
    game.game_mode = 'faf'
    game.id = 42
    game_service.games[42] = game
    lobbyconnection.player = players.hosting
    players.hosting.in_game = False
    test_game_info['uid'] = 42

    lobbyconnection.command_game_join(test_game_info)
    expected_reply = {
        'command': 'game_launch',
        'mod': 'faf',
        'uid': 42,
        'args': ['/numgames {}'.format(players.hosting.numGames)]
    }
    mock_protocol.send_message.assert_called_with(expected_reply)


def test_command_game_host_calls_host_game_invalid_title(lobbyconnection,
                                                         mock_games,
                                                         test_game_info_invalid):
    lobbyconnection.sendJSON = mock.Mock()
    mock_games.create_game = mock.Mock()
    lobbyconnection.command_game_host(test_game_info_invalid)
    assert mock_games.create_game.mock_calls == []
    lobbyconnection.sendJSON.assert_called_once_with(dict(command="notice", style="error", text="Non-ascii characters in game name detected."))


def test_abort(loop, mocker, lobbyconnection):
    proto = mocker.patch.object(lobbyconnection, 'protocol')

    lobbyconnection.abort()

    proto.writer.close.assert_any_call()


def test_send_game_list(mocker, lobbyconnection, game_stats_service):
    protocol = mocker.patch.object(lobbyconnection, 'protocol')
    games = mocker.patch.object(lobbyconnection, 'game_service')  # type: GameService
    game1, game2 = mock.create_autospec(Game(42, mock.Mock(), game_stats_service)),\
                   mock.create_autospec(Game(22, mock.Mock(), game_stats_service))

    games.open_games = [game1, game2]

    lobbyconnection.send_game_list()

    protocol.send_message.assert_any_call({'command': 'game_info',
                                           'games': [game1.to_dict(), game2.to_dict()]})

async def test_register_invalid_email(mocker, lobbyconnection):
    protocol = mocker.patch.object(lobbyconnection, 'protocol')
    await lobbyconnection.command_create_account({
        'login': 'Chris',
        'email': "SPLORK",
        'password': "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
    })

    protocol.send_message.assert_any_call({
        'command': 'registration_response',
        'result': "FAILURE",
        'error': "Please use a valid email address." # TODO: Yay localisation :/
    })


async def test_register_disposable_email(mocker, lobbyconnection):
    lobbyconnection.generate_expiring_request = mock.Mock()
    await lobbyconnection.command_create_account({
        'login': 'Chris',
        'email': "chris@5minutemail.com",
        'password': "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
    })

    lobbyconnection.generate_expiring_request.assert_not_called()


async def test_register_non_disposable_email(mocker, lobbyconnection: LobbyConnection):
    lobbyconnection.generate_expiring_request = mock.Mock(return_value=('iv', 'ciphertext', 'verification_hex'))
    lobbyconnection.player_service.has_blacklisted_domain.return_value = False

    await lobbyconnection.command_create_account({
        'login': 'Chris',
        'email': "chriskitching@linux.com",
        'password': "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
    })

    assert lobbyconnection.generate_expiring_request.mock_calls

def test_send_mod_list(mocker, lobbyconnection, mock_games):
    protocol = mocker.patch.object(lobbyconnection, 'protocol')

    lobbyconnection.send_mod_list()

    protocol.send_messages.assert_called_with(mock_games.all_game_modes())

@asyncio.coroutine
def test_command_admin_closelobby(mocker, lobbyconnection):
    mocker.patch.object(lobbyconnection, 'protocol')
    mocker.patch.object(lobbyconnection, '_logger')
    config = mocker.patch('server.lobbyconnection.config')
    player = mocker.patch.object(lobbyconnection, 'player')
    player.login = 'Sheeo'
    player.admin = True
    tuna = mock.Mock()
    tuna.id = 55
    lobbyconnection.player_service = {1: player, 55: tuna}

    yield from lobbyconnection.command_admin({
        'command': 'admin',
        'action': 'closelobby',
        'user_id': 55
    })

    tuna.lobby_connection.kick.assert_any_call(
        message=("Your client was closed by an administrator (Sheeo). "
              "Please refer to our rules for the lobby/game here {rule_link}."
              .format(rule_link=config.RULE_LINK))
    )

@asyncio.coroutine
def test_command_admin_closeFA(mocker, lobbyconnection):
    mocker.patch.object(lobbyconnection, 'protocol')
    mocker.patch.object(lobbyconnection, '_logger')
    config = mocker.patch('server.lobbyconnection.config')
    player = mocker.patch.object(lobbyconnection, 'player')
    player.login = 'Sheeo'
    player.id = 42
    tuna = mock.Mock()
    tuna.id = 55
    lobbyconnection.player_service = {42: player, 55: tuna}

    yield from lobbyconnection.command_admin({
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

async def test_game_subscription(lobbyconnection: LobbyConnection):
    game = Mock()
    game.handle_action = CoroMock()
    lobbyconnection.game_connection = game
    lobbyconnection.ensure_authenticated = lambda _: True

    await lobbyconnection.on_message_received({'command': 'test',
                                               'args': ['foo', 42],
                                               'target': 'game'})

    game.handle_action.assert_called_with('test', ['foo', 42])

async def test_command_avatar_list(mocker, lobbyconnection: LobbyConnection, mock_player: Player):
    protocol = mocker.patch.object(lobbyconnection, 'protocol')
    lobbyconnection.player = mock_player
    lobbyconnection.player.id = 2  # Dostya test user

    await lobbyconnection.command_avatar({
        'action': 'list_avatar'
    })

    protocol.send_message.assert_any_call({
        "command": "avatar",
        "avatarlist": [{'url': 'http://content.faforever.com/faf/avatars/qai2.png', 'tooltip': 'QAI'}]
    })

async def test_command_avatar_select(mocker, lobbyconnection: LobbyConnection, mock_player: Player):
    lobbyconnection.player = mock_player
    lobbyconnection.player.id = 2  # Dostya test user

    await lobbyconnection.command_avatar({
        'action': 'select',
        'avatar': "http://content.faforever.com/faf/avatars/qai2.png"
    })

    async with db.db_pool.get() as conn:
        cursor = await conn.cursor()
        await cursor.execute("SELECT selected from avatars where idUser=2")
        result = await cursor.fetchone()
        assert result == (1,)
