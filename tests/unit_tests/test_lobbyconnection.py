from hashlib import sha256
from unittest import mock
from unittest.mock import Mock

import asynctest
import pytest
from aiohttp import web
from asynctest import CoroutineMock
from sqlalchemy import and_, select

from server import GameState, VisibilityState, config
from server.abc.base_game import InitMode
from server.db.models import ban, friends_and_foes
from server.game_service import GameService
from server.gameconnection import GameConnection
from server.games import CustomGame, Game
from server.geoip_service import GeoIpService
from server.ice_servers.nts import TwilioNTS
from server.ladder_service import LadderService
from server.lobbyconnection import ClientError, LobbyConnection
from server.matchmaker import Search
from server.player_service import PlayerService
from server.players import PlayerState
from server.protocol import DisconnectedError, QDataStreamProtocol
from server.rating import RatingType
from server.types import Address

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def test_game_info():
    return {
        'title': 'Test game',
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
        'visibility': VisibilityState.to_string(VisibilityState.PUBLIC),
        'mod': 'faf',
        'mapname': 'scmp_007',
        'password': None,
        'lobby_rating': 1,
        'options': []
    }


@pytest.fixture
def mock_player(player_factory):
    return player_factory('Dummy', player_id=42, with_lobby_connection=False)


@pytest.fixture
def mock_nts_client():
    return asynctest.create_autospec(TwilioNTS)


@pytest.fixture
def mock_players():
    return asynctest.create_autospec(PlayerService)


@pytest.fixture
def mock_games():
    return asynctest.create_autospec(GameService)


@pytest.fixture
def mock_protocol():
    return asynctest.create_autospec(QDataStreamProtocol(mock.Mock(), mock.Mock()))


@pytest.fixture
def mock_geoip():
    return asynctest.create_autospec(GeoIpService)


@pytest.fixture
def lobbyconnection(
    event_loop,
    database,
    mock_protocol,
    mock_games,
    mock_players,
    mock_player,
    mock_geoip,
    mock_nts_client
):
    lc = LobbyConnection(
        database=database,
        geoip=mock_geoip,
        game_service=mock_games,
        players=mock_players,
        nts_client=mock_nts_client,
        ladder_service=asynctest.create_autospec(LadderService)
    )

    lc.player = mock_player
    lc.protocol = mock_protocol
    lc.player_service.fetch_player_data = CoroutineMock()
    lc.peer_address = Address('127.0.0.1', 1234)
    lc._authenticated = True
    return lc


@pytest.fixture
def policy_server(event_loop):
    host = 'localhost'
    port = 6080

    app = web.Application()
    routes = web.RouteTableDef()

    @routes.post('/verify')
    async def token(request):
        data = await request.json()
        return web.json_response({'result': data.get('uid_hash')})

    app.add_routes(routes)

    runner = web.AppRunner(app)

    async def start_app():
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

    event_loop.run_until_complete(start_app())
    yield (host, port)
    event_loop.run_until_complete(runner.cleanup())


async def test_unauthenticated_calls_abort(lobbyconnection, test_game_info):
    lobbyconnection._authenticated = False
    lobbyconnection.abort = CoroutineMock()

    await lobbyconnection.on_message_received({
        "command": "game_host",
        **test_game_info
    })

    lobbyconnection.abort.assert_called_once_with(
        "Message invalid for unauthenticated connection: game_host"
    )


async def test_bad_command_calls_abort(lobbyconnection):
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.abort = CoroutineMock()

    await lobbyconnection.on_message_received({
        "command": "this_isnt_real"
    })

    lobbyconnection.send.assert_called_once_with({"command": "invalid"})
    lobbyconnection.abort.assert_called_once_with("Error processing command")


async def test_command_pong_does_nothing(lobbyconnection):
    lobbyconnection.send = CoroutineMock()

    await lobbyconnection.on_message_received({
        "command": "pong"
    })

    lobbyconnection.send.assert_not_called()


async def test_command_create_account_returns_error(lobbyconnection):
    lobbyconnection.send = CoroutineMock()

    await lobbyconnection.on_message_received({
        "command": "create_account"
    })

    lobbyconnection.send.assert_called_once_with({
        "command": "notice",
        "style": "error",
        "text": ("FAF no longer supports direct registration. "
                 "Please use the website to register.")
    })


async def test_double_login(lobbyconnection, mock_players, player_factory):
    lobbyconnection.check_policy_conformity = CoroutineMock(return_value=True)
    old_player = player_factory(with_lobby_connection=True)
    old_player.lobby_connection.player = old_player
    mock_players.get_player.return_value = old_player

    await lobbyconnection.on_message_received({
        "command": "hello",
        "login": "test",
        "password": sha256(b"test_password").hexdigest(),
        "unique_id": "blah"
    })

    old_player.lobby_connection.send_warning.assert_called_with(
        "You have been signed out because you signed in elsewhere.",
        fatal=True
    )
    # This should only be reset in abort, which is mocked for this test
    assert old_player.lobby_connection.player is not None


async def test_double_login_disconnected(lobbyconnection, mock_players, player_factory):
    lobbyconnection.abort = CoroutineMock()
    lobbyconnection.check_policy_conformity = CoroutineMock(return_value=True)
    old_player = player_factory(with_lobby_connection=True)
    mock_players.get_player.return_value = old_player

    old_player.lobby_connection.send_warning.side_effect = DisconnectedError("Test disconnect")

    # Should not raise
    await lobbyconnection.on_message_received({
        "command": "hello",
        "login": "test",
        "password": sha256(b"test_password").hexdigest(),
        "unique_id": "blah"
    })

    lobbyconnection.abort.assert_not_called()


async def test_command_game_host_creates_game(lobbyconnection,
                                              mock_games,
                                              test_game_info,
                                              players):
    lobbyconnection.player = players.hosting
    await lobbyconnection.on_message_received({
        "command": "game_host",
        **test_game_info
    })
    expected_call = {
        'game_mode': 'faf',
        'name': test_game_info['title'],
        'host': players.hosting,
        'visibility': VisibilityState.PUBLIC,
        'password': test_game_info['password'],
        'mapname': test_game_info['mapname'],
    }
    mock_games.create_game.assert_called_with(**expected_call)


async def test_launch_game(lobbyconnection, game, player_factory):
    old_game_conn = asynctest.create_autospec(GameConnection)

    lobbyconnection.player = player_factory()
    lobbyconnection.game_connection = old_game_conn
    lobbyconnection.send = CoroutineMock()
    await lobbyconnection.launch_game(game)

    # Verify all side effects of launch_game here
    old_game_conn.abort.assert_called_with("Player launched a new game")
    assert lobbyconnection.game_connection is not None
    assert lobbyconnection.game_connection.game == game
    assert lobbyconnection.player.game == game
    assert lobbyconnection.player.game_connection == lobbyconnection.game_connection
    assert lobbyconnection.game_connection.player == lobbyconnection.player
    assert lobbyconnection.player.state == PlayerState.JOINING
    lobbyconnection.send.assert_called_once()


async def test_command_game_host_creates_correct_game(
        lobbyconnection, game_service, test_game_info, players):
    lobbyconnection.player = players.hosting
    lobbyconnection.game_service = game_service
    lobbyconnection.launch_game = CoroutineMock()

    await lobbyconnection.on_message_received({
        "command": "game_host",
        **test_game_info
    })
    args_list = lobbyconnection.launch_game.call_args_list
    assert len(args_list) == 1
    args, kwargs = args_list[0]
    assert isinstance(args[0], CustomGame)


async def test_command_game_join_calls_join_game(mocker,
                                                 database,
                                                 lobbyconnection,
                                                 game_service,
                                                 test_game_info,
                                                 players,
                                                 game_stats_service):
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.game_service = game_service
    game = Game(42, database, game_service, game_stats_service)
    game.state = GameState.LOBBY
    game.password = None
    game.game_mode = 'faf'
    game.id = 42
    game.name = "Test Game Name"
    game_service._games[42] = game
    lobbyconnection.player = players.hosting
    test_game_info['uid'] = 42

    await lobbyconnection.on_message_received({
        "command": "game_join",
        **test_game_info
    })
    expected_reply = {
        "command": "game_launch",
        "args": ["/numgames", players.hosting.game_count[RatingType.GLOBAL]],
        "uid": 42,
        "mod": "faf",
        "name": "Test Game Name",
        "init_mode": InitMode.NORMAL_LOBBY.value,
    }
    lobbyconnection.send.assert_called_with(expected_reply)


async def test_command_game_join_uid_as_str(mocker,
                                            database,
                                            lobbyconnection,
                                            game_service,
                                            test_game_info,
                                            players,
                                            game_stats_service):
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.game_service = game_service
    game = Game(42, database, game_service, game_stats_service)
    game.state = GameState.LOBBY
    game.password = None
    game.game_mode = 'faf'
    game.id = 42
    game.name = "Test Game Name"
    game_service._games[42] = game
    lobbyconnection.player = players.hosting
    test_game_info['uid'] = '42'  # Pass in uid as string

    await lobbyconnection.on_message_received({
        "command": "game_join",
        **test_game_info
    })
    expected_reply = {
        'command': 'game_launch',
        'args': ['/numgames', players.hosting.game_count[RatingType.GLOBAL]],
        'mod': 'faf',
        'uid': 42,
        'name': 'Test Game Name',
        'init_mode': InitMode.NORMAL_LOBBY.value,
    }
    lobbyconnection.send.assert_called_with(expected_reply)


async def test_command_game_join_without_password(
    lobbyconnection,
    database,
    game_service,
    test_game_info,
    players,
    game_stats_service
):
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.game_service = game_service
    game = mock.create_autospec(Game)
    game.state = GameState.LOBBY
    game.init_mode = InitMode.NORMAL_LOBBY
    game.password = 'password'
    game.game_mode = 'faf'
    game.id = 42
    game_service._games[42] = game
    lobbyconnection.player = players.hosting
    test_game_info['uid'] = 42
    del test_game_info['password']

    await lobbyconnection.on_message_received({
        "command": "game_join",
        **test_game_info
    })
    lobbyconnection.send.assert_called_once_with({
        "command": "notice",
        "style": "info",
        "text": "Bad password (it's case sensitive)."
    })


async def test_command_game_join_game_not_found(
    lobbyconnection,
    game_service,
    test_game_info,
    players
):
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.game_service = game_service
    lobbyconnection.player = players.hosting
    test_game_info['uid'] = 42

    await lobbyconnection.on_message_received({
        "command": "game_join",
        **test_game_info
    })
    lobbyconnection.send.assert_called_once_with({
        "command": "notice",
        "style": "info",
        "text": "The host has left the game."
    })


async def test_command_game_join_game_bad_init_mode(
    lobbyconnection,
    game_service,
    test_game_info,
    players
):
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.game_service = game_service
    game = mock.create_autospec(Game)
    game.state = GameState.LOBBY
    game.init_mode = InitMode.AUTO_LOBBY
    game.id = 42
    game_service._games[42] = game
    lobbyconnection.player = players.hosting
    test_game_info['uid'] = 42

    await lobbyconnection.on_message_received({
        "command": "game_join",
        **test_game_info
    })
    lobbyconnection.send.assert_called_once_with({
        "command": "notice",
        "style": "error",
        "text": "The game cannot be joined in this way."
    })


async def test_command_game_host_calls_host_game_invalid_title(lobbyconnection,
                                                               mock_games,
                                                               test_game_info_invalid):
    lobbyconnection.send = CoroutineMock()
    mock_games.create_game = mock.Mock()
    await lobbyconnection.on_message_received({
        "command": "game_host",
        **test_game_info_invalid
    })
    assert mock_games.create_game.mock_calls == []
    lobbyconnection.send.assert_called_once_with(
        dict(command="notice", style="error", text="Non-ascii characters in game name detected."))


async def test_abort(mocker, lobbyconnection):
    lobbyconnection.protocol.close = CoroutineMock()
    await lobbyconnection.abort()

    lobbyconnection.protocol.close.assert_any_call()


async def test_send_game_list(mocker, database, lobbyconnection, game_stats_service):
    games = mocker.patch.object(lobbyconnection, 'game_service')  # type: GameService
    game1, game2 = mock.create_autospec(Game(42, database, mock.Mock(), game_stats_service)), \
                   mock.create_autospec(Game(22, database, mock.Mock(), game_stats_service))

    games.open_games = [game1, game2]
    lobbyconnection.send = CoroutineMock()

    await lobbyconnection.send_game_list()

    lobbyconnection.send.assert_any_call({
        'command': 'game_info',
        'games': [game1.to_dict(), game2.to_dict()]
    })


async def test_coop_list(mocker, lobbyconnection):
    await lobbyconnection.command_coop_list({})

    args = lobbyconnection.protocol.send_messages.call_args_list
    assert len(args) == 1
    coop_maps = args[0][0][0]
    for info in coop_maps:
        del info['uid']
    assert coop_maps == [
        {
            "command": "coop_info",
            "name": "FA Campaign map",
            "description": "A map from the FA campaign",
            "filename": "maps/scmp_coop_123.v0002.zip",
            "featured_mod": "coop",
            "type": "FA Campaign"
        },
        {
            "command": "coop_info",
            "name": "Aeon Campaign map",
            "description": "A map from the Aeon campaign",
            "filename": "maps/scmp_coop_124.v0000.zip",
            "featured_mod": "coop",
            "type": "Aeon Vanilla Campaign"
        },
        {
            "command": "coop_info",
            "name": "Cybran Campaign map",
            "description": "A map from the Cybran campaign",
            "filename": "maps/scmp_coop_125.v0001.zip",
            "featured_mod": "coop",
            "type": "Cybran Vanilla Campaign"
        },
        {
            "command": "coop_info",
            "name": "UEF Campaign map",
            "description": "A map from the UEF campaign",
            "filename": "maps/scmp_coop_126.v0099.zip",
            "featured_mod": "coop",
            "type": "UEF Vanilla Campaign"
        },
        {
            "command": "coop_info",
            "name": "Prothyon - 16",
            "description": "Prothyon - 16 is a secret UEF facility...",
            "filename": "maps/prothyon16.v0005.zip",
            "featured_mod": "coop",
            "type": "Custom Missions"
        }
    ]


async def test_command_admin_closelobby(mocker, lobbyconnection, player_factory):
    player = lobbyconnection.player
    player.id = 1
    tuna = player_factory("Tuna", player_id=55, with_lobby_connection=True)
    data = {
        player.id: player,
        tuna.id: tuna
    }
    lobbyconnection.player_service.__getitem__.side_effect = data.__getitem__

    await lobbyconnection.on_message_received({
        'command': 'admin',
        'action': 'closelobby',
        'user_id': 55
    })

    tuna.lobby_connection.kick.assert_any_call()


async def test_command_admin_closeFA(lobbyconnection, player_factory):
    player = lobbyconnection.player
    player.id = 1
    tuna = player_factory("Tuna", player_id=55, with_lobby_connection=True)
    data = {
        player.id: player,
        tuna.id: tuna
    }
    lobbyconnection.player_service.__getitem__.side_effect = data.__getitem__

    await lobbyconnection.on_message_received({
        'command': 'admin',
        'action': 'closeFA',
        'user_id': tuna.id
    })

    tuna.lobby_connection.send.assert_any_call({
        "command": "notice",
        "style": "kill",
    })


async def test_game_subscription(lobbyconnection: LobbyConnection):
    game = Mock()
    game.handle_action = CoroutineMock()
    lobbyconnection.game_connection = game

    await lobbyconnection.on_message_received({
        'command': 'test',
        'args': ['foo', 42],
        'target': 'game'
    })

    game.handle_action.assert_called_with('test', ['foo', 42])


async def test_command_avatar_list(mocker, lobbyconnection: LobbyConnection):
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.player.id = 2  # Dostya test user

    await lobbyconnection.on_message_received({
        'command': 'avatar',
        'action': 'list_avatar'
    })

    lobbyconnection.send.assert_any_call({
        "command": "avatar",
        "avatarlist": [{'url': 'https://content.faforever.com/faf/avatars/qai2.png', 'tooltip': 'QAI'}, {'url': 'https://content.faforever.com/faf/avatars/UEF.png', 'tooltip': 'UEF'}]
    })


async def test_command_avatar_select(mocker, database, lobbyconnection: LobbyConnection):
    lobbyconnection.player.id = 2  # Dostya test user

    await lobbyconnection.on_message_received({
        'command': 'avatar',
        'action': 'select',
        'avatar': "https://content.faforever.com/faf/avatars/qai2.png"
    })

    async with database.acquire() as conn:
        result = await conn.execute("SELECT selected from avatars where idUser=2")
        row = await result.fetchone()
        assert row[0] == 1


async def get_friends(player_id, database):
    async with database.acquire() as conn:
        result = await conn.execute(
            select([friends_and_foes.c.subject_id]).where(
                and_(
                    friends_and_foes.c.user_id == player_id,
                    friends_and_foes.c.status == 'FRIEND'
                )
            )
        )

        return [row['subject_id'] async for row in result]


async def test_command_social_add_friend(lobbyconnection, database):
    lobbyconnection.player.id = 1

    friends = await get_friends(lobbyconnection.player.id, database)
    assert friends == []

    await lobbyconnection.on_message_received({
        'command': 'social_add',
        'friend': 2
    })

    friends = await get_friends(lobbyconnection.player.id, database)
    assert friends == [2]


async def test_command_social_remove_friend(lobbyconnection, database):
    lobbyconnection.player.id = 2

    friends = await get_friends(lobbyconnection.player.id, database)
    assert friends == [1]

    await lobbyconnection.on_message_received({
        'command': 'social_remove',
        'friend': 1
    })

    friends = await get_friends(lobbyconnection.player.id, database)
    assert friends == []


async def test_command_ice_servers(
    lobbyconnection: LobbyConnection,
    mock_nts_client
):
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.coturn_generator.server_tokens = Mock(
        return_value=["coturn_tokens"]
    )
    mock_nts_client.server_tokens.return_value = ["twilio_tokens"]

    await lobbyconnection.on_message_received({"command": "ice_servers"})

    mock_nts_client.server_tokens.assert_called_once()
    lobbyconnection.send.assert_called_once_with({
        "command": "ice_servers",
        "ice_servers": ["coturn_tokens", "twilio_tokens"],
        "ttl": config.TWILIO_TTL
    })


async def test_broadcast(lobbyconnection: LobbyConnection, player_factory):
    player = lobbyconnection.player
    player.lobby_connection = lobbyconnection
    player.id = 1
    tuna = player_factory("Tuna", player_id=55, with_lobby_connection=True)
    data = {
        player.id: player,
        tuna.id: tuna
    }
    lobbyconnection.player_service.__iter__.side_effect = data.values().__iter__
    lobbyconnection.send_warning = CoroutineMock()

    await lobbyconnection.on_message_received({
        'command': 'admin',
        'action': 'broadcast',
        'message': "This is a test message"
    })

    player.lobby_connection.send_warning.assert_called_with("This is a test message")
    tuna.lobby_connection.send_warning.assert_called_with("This is a test message")


async def test_broadcast_during_disconnect(lobbyconnection: LobbyConnection, player_factory):
    player = lobbyconnection.player
    player.lobby_connection = lobbyconnection
    player.id = 1
    # To simulate when a player has been recently disconnected so that they
    # still appear in the player_service list, but their lobby_connection
    # object has already been destroyed
    tuna = player_factory("Tuna", player_id=55, with_lobby_connection=False)
    data = {
        player.id: player,
        tuna.id: tuna
    }
    lobbyconnection.player_service.__iter__.side_effect = data.values().__iter__
    lobbyconnection.send_warning = CoroutineMock()

    # This should not leak any exceptions
    await lobbyconnection.on_message_received({
        'command': 'admin',
        'action': 'broadcast',
        'message': "This is a test message"
    })

    player.lobby_connection.send_warning.assert_called_with("This is a test message")


async def test_broadcast_connection_error(lobbyconnection: LobbyConnection, player_factory):
    player = lobbyconnection.player
    player.lobby_connection = lobbyconnection
    player.id = 1
    tuna = player_factory("Tuna", player_id=55, with_lobby_connection=True)
    tuna.lobby_connection.send_warning.side_effect = ConnectionError("Some error")
    data = {
        player.id: player,
        tuna.id: tuna
    }
    lobbyconnection.player_service.__iter__.side_effect = data.values().__iter__
    lobbyconnection.send_warning = CoroutineMock()

    # This should not leak any exceptions
    await lobbyconnection.on_message_received({
        'command': 'admin',
        'action': 'broadcast',
        'message': "This is a test message"
    })

    player.lobby_connection.send_warning.assert_called_with("This is a test message")


async def test_game_connection_not_restored_if_no_such_game_exists(lobbyconnection: LobbyConnection, mocker):
    del lobbyconnection.player.game_connection
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.player.state = PlayerState.IDLE
    await lobbyconnection.on_message_received({
        'command': 'restore_game_session',
        'game_id': 123
    })

    assert not lobbyconnection.player.game_connection
    assert lobbyconnection.player.state == PlayerState.IDLE

    lobbyconnection.send.assert_any_call({
        "command": "notice",
        "style": "info",
        "text": "The game you were connected to does no longer exist"
    })


@pytest.mark.parametrize("game_state", [GameState.INITIALIZING, GameState.ENDED])
async def test_game_connection_not_restored_if_game_state_prohibits(
    lobbyconnection: LobbyConnection,
    game_service: GameService,
    game_stats_service,
    game_state,
    mocker,
    database
):
    del lobbyconnection.player.game_connection
    lobbyconnection.send = CoroutineMock()
    lobbyconnection.player.state = PlayerState.IDLE
    lobbyconnection.game_service = game_service
    game = mock.create_autospec(Game(42, database, game_service, game_stats_service))
    game.state = game_state
    game.password = None
    game.game_mode = 'faf'
    game.id = 42
    game_service._games[42] = game

    await lobbyconnection.on_message_received({
        'command': 'restore_game_session',
        'game_id': 42
    })

    assert not lobbyconnection.game_connection
    assert lobbyconnection.player.state == PlayerState.IDLE

    lobbyconnection.send.assert_any_call({
        "command": "notice",
        "style": "info",
        "text": "The game you were connected to is no longer available"
    })


@pytest.mark.parametrize("game_state", [GameState.LIVE, GameState.LOBBY])
async def test_game_connection_restored_if_game_exists(
    lobbyconnection: LobbyConnection,
    game_service: GameService,
    game_stats_service,
    game_state,
    database
):
    del lobbyconnection.player.game_connection
    lobbyconnection.player.state = PlayerState.IDLE
    lobbyconnection.game_service = game_service
    game = mock.create_autospec(Game(42, database, game_service, game_stats_service))
    game.state = game_state
    game.password = None
    game.game_mode = 'faf'
    game.id = 42
    game_service._games[42] = game

    await lobbyconnection.on_message_received({
        'command': 'restore_game_session',
        'game_id': 42
    })

    assert lobbyconnection.game_connection
    assert lobbyconnection.player.state is PlayerState.PLAYING
    assert lobbyconnection.player.game is game


async def test_command_game_matchmaking(lobbyconnection):
    lobbyconnection.player.id = 1

    await lobbyconnection.on_message_received({
        'command': 'game_matchmaking',
        'state': 'stop'
    })

    lobbyconnection.ladder_service.cancel_search.assert_called_with(
        lobbyconnection.player,
        "ladder1v1"
    )


async def test_command_matchmaker_info(
    lobbyconnection,
    ladder_service,
    queue_factory,
    player_factory
):
    queue = queue_factory("test", rating_type=RatingType.LADDER_1V1)
    queue.timer.next_queue_pop = 1_562_000_000
    queue.push(Search([
        player_factory(player_id=1, ladder_rating=(2000, 100), ladder_games=200),
    ]))
    queue.push(Search([
        player_factory(player_id=2, ladder_rating=(500, 120), ladder_games=100),
        player_factory(player_id=3, ladder_rating=(1500, 500), ladder_games=0),
    ]))
    queue.push(Search([
        player_factory(player_id=4, ladder_rating=(1000, 100), ladder_games=500),
        player_factory(player_id=5, ladder_rating=(1300, 100), ladder_games=200),
        player_factory(player_id=6, ladder_rating=(2000, 100), ladder_games=1000),
    ]))

    lobbyconnection.ladder_service.queues = {
        "test": queue
    }
    lobbyconnection.send = CoroutineMock()
    await lobbyconnection.on_message_received({
        "command": "matchmaker_info"
    })

    lobbyconnection.send.assert_called_with({
        "command": "matchmaker_info",
        "queues": [
            {
                "queue_name": "test",
                "queue_pop_time": "2019-07-01T16:53:20+00:00",
                "team_size": 1,
                "num_players": 6,
                "boundary_80s": [(1800, 2200), (300, 700), (800, 1200)],
                "boundary_75s": [(1900, 2100), (400, 600), (900, 1100)]
            }
        ]
    })


async def test_connection_lost(lobbyconnection):
    await lobbyconnection.on_connection_lost()

    lobbyconnection.ladder_service.on_connection_lost.assert_called_once_with(lobbyconnection.player)
    lobbyconnection.player_service.remove_player.assert_called_once_with(lobbyconnection.player)


async def test_connection_lost_no_player(lobbyconnection):
    lobbyconnection.player = None
    await lobbyconnection.on_connection_lost()

    lobbyconnection.ladder_service.on_connection_lost.assert_not_called()
    lobbyconnection.player_service.remove_player.assert_not_called()


async def test_connection_lost_send(lobbyconnection, mock_protocol):
    await lobbyconnection.on_connection_lost()

    await lobbyconnection.send({"command": "Some Message"})

    mock_protocol.send_message.assert_not_called()
    mock_protocol.send_messages.assert_not_called()
    mock_protocol.send_raw.assert_not_called()


async def test_check_policy_conformity(lobbyconnection, policy_server):
    host, port = policy_server
    config.FAF_POLICY_SERVER_BASE_URL = f"http://{host}:{port}"

    honest = await lobbyconnection.check_policy_conformity(1, "honest", session=100)
    assert honest is True


async def test_check_policy_conformity_fraudulent(lobbyconnection, policy_server, database):
    host, port = policy_server
    config.FAF_POLICY_SERVER_BASE_URL = f"http://{host}:{port}"

    # 42 is not a valid player ID which should cause a SQL constraint error
    lobbyconnection.abort = CoroutineMock()
    with pytest.raises(ClientError):
        await lobbyconnection.check_policy_conformity(42, "fraudulent", session=100)

    lobbyconnection.abort = CoroutineMock()
    player_id = 200
    honest = await lobbyconnection.check_policy_conformity(player_id, "fraudulent", session=100)
    assert honest is False
    lobbyconnection.abort.assert_called_once()

    # Check that the user has a ban entry in the database
    async with database.acquire() as conn:
        result = await conn.execute(select([ban.c.reason]).where(
            ban.c.player_id == player_id
        ))
        rows = await result.fetchall()
        assert rows is not None
        assert rows[-1][ban.c.reason] == "Auto-banned because of fraudulent login attempt"


async def test_check_policy_conformity_fatal(lobbyconnection, policy_server):
    host, port = policy_server
    config.FAF_POLICY_SERVER_BASE_URL = f"http://{host}:{port}"

    for result in ('vm', 'already_associated', 'fraudulent'):
        lobbyconnection.abort = CoroutineMock()
        honest = await lobbyconnection.check_policy_conformity(1, result, session=100)
        assert honest is False
        lobbyconnection.abort.assert_called_once()
