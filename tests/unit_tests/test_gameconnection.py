import asyncio

import ujson

import mock
import pytest

from server import proxy_map
from server.connectivity import Connectivity
from server.gameconnection import GameConnection
from server.games import Game

slow = pytest.mark.slow

@asyncio.coroutine
def test_on_connection_made_no_player(game_connection):
    mock_users = mock.Mock()
    mock_users.find_by_ip_and_session = mock.Mock(return_value=None)
    game_connection.users = mock_users
    game_connection.abort = mock.Mock()

    yield from game_connection.on_connection_made(mock.Mock(), ('127.0.0.1', 5123))
    yield from game_connection.handle_action('Authenticate', 42)

    game_connection.abort.assert_any_call()

@asyncio.coroutine
def test_on_connection_made_no_game(game_connection, players):
    mock_users = mock.Mock()
    mock_users.find_by_ip_and_session = mock.Mock(return_value=players.hosting)
    players.hosting.game = None
    game_connection.users = mock_users
    game_connection.abort = mock.Mock()

    yield from game_connection.on_connection_made(mock.Mock(), ('127.0.0.1', 5123))
    yield from game_connection.handle_action('Authenticate', 42)

    game_connection.abort.assert_any_call()

@asyncio.coroutine
def test_ping_miss(game_connection):
    game_connection.abort = mock.Mock()
    game_connection.last_pong = 0

    asyncio.async(game_connection.ping())
    yield from asyncio.sleep(0.1)

    game_connection.abort.assert_any_call()

@asyncio.coroutine
def test_ping_hit(game_connection):
    game_connection.abort = mock.Mock()
    protocol = mock.Mock()
    game_connection.protocol = protocol

    asyncio.async(game_connection.ping())
    yield from asyncio.sleep(0.1)

    protocol.send_message.assert_any_call({
        'key': 'ping',
        'commands': []
    })
    for i in range(1, 3):
        game_connection.handle_action('pong', [])
        game_connection.ping()
    assert game_connection.abort.mock_calls == []


def test_abort(game_connection, game, players, connected_game_socket):
    game_connection.player = players.hosting
    game_connection.game = game
    game_connection.socket = connected_game_socket

    game_connection.abort()

    game.remove_game_connection.assert_called_with(game_connection)
    players.hosting.lobby_connection.sendJSON.assert_called_with(
        dict(command='notice',
             style='kill')
    )

@asyncio.coroutine
def test_handle_action_GameState_idle_adds_connection(game_connection, players, game):
    players.joining.game = game
    game_connection.protocol = mock.Mock()
    game_connection.player = players.hosting
    game_connection.game = game

    yield from game_connection.handle_action('GameState', ['Idle'])

    game.add_game_connection.assert_called_with(game_connection)

@asyncio.coroutine
def test_handle_action_GameState_idle_non_searching_player_aborts(game_connection, players):
    game_connection.player = players.hosting
    game_connection.lobby = mock.Mock()
    game_connection.abort = mock.Mock()
    players.hosting.action = None

    yield from game_connection.handle_action('GameState', ['Idle'])

    game_connection.abort.assert_any_call()

@asyncio.coroutine
def test_handle_action_GameState_idle_as_peer_sends_CreateLobby(game_connection, players):
    """
    :type game_connection: GameConnection
    """
    protocol = mock.Mock()
    game_connection.protocol = protocol
    game_connection.player = players.joining

    yield from game_connection.handle_action('GameState', ['Idle'])

    protocol.send_message.assert_any_call({'key': 'CreateLobby',
                                           'commands': [0, players.joining.gamePort,
                                            players.joining.login,
                                            players.joining.id,
                                            1]})

@asyncio.coroutine
def test_handle_action_GameState_idle_as_host_sends_CreateLobby(game_connection, players):
    """
    :type game_connection: GameConnection
    """
    protocol = mock.Mock()
    game_connection.protocol = protocol
    game_connection.player = players.hosting

    yield from game_connection.handle_action('GameState', ['Idle'])

    protocol.send_message.assert_any_call({'key': 'CreateLobby',
                                           'commands': [0, players.hosting.gamePort,
                                                        players.hosting.login,
                                                        players.hosting.id,
                                                        1]})


@slow
def test_handle_action_GameState_lobby_sends_HostGame(game_connection, loop, players, game):
    """
    :type game_connection: GameConnection
    """
    with mock.patch('server.gameconnection.TestPeer') as peer_test:
        fut = asyncio.Future()
        fut.set_result(Connectivity.PUBLIC)
        peer_test().__enter__().determine_connectivity.return_value = fut
        protocol = mock.Mock()
        game_connection.protocol = protocol
        game_connection.player = players.hosting
        game.mapName = 'some_map'

        result = asyncio.async(game_connection.handle_action('GameState', ['Lobby']))
        loop.run_until_complete(result)

        protocol.send_message.assert_any_call({'key': 'HostGame',
                                               'commands': [game.mapName]})


def test_handle_action_GameState_lobby_calls_ConnectToHost(game_connection, loop, players, game):
    """
    :type game_connection: GameConnection
    """
    with mock.patch('server.gameconnection.TestPeer') as peer_test:
        fut = asyncio.Future()
        fut.set_result(Connectivity.PUBLIC)
        peer_test().__enter__().determine_connectivity.return_value = fut
        game_connection.send_message = mock.MagicMock()
        game_connection.ConnectToHost = mock.Mock()
        game_connection.player = players.joining
        players.joining.game = game
        game.hostPlayer = players.hosting
        game.mapName = 'some_map'

        result = asyncio.async(game_connection.handle_action('GameState', ['Lobby']))
        loop.run_until_complete(result)

        game_connection.ConnectToHost.assert_called_with(players.hosting.game_connection)

def test_handle_action_GameState_launching_calls_launch(game_connection, loop, players, game):
    """
    :type game_connection: GameConnection
    """
    game_connection.player = players.hosting
    game_connection.game = game

    result = asyncio.async(game_connection.handle_action('GameState', ['Launching']))
    loop.run_until_complete(result)

    game.launch.assert_any_call()


def test_handle_action_PlayerOption(game, loop, game_connection):
    """
    :type game Game
    :type game_connection GameConnection
    """
    result = asyncio.async(game_connection.handle_action('PlayerOption', [1, 'Color', 2]))
    loop.run_until_complete(result)
    game.set_player_option.assert_called_once_with(1, 'Color', 2)


def test_handle_action_PlayerOption_malformed_no_raise(game_connection, loop):
    """
    :type game_connection GameConnection
    """
    result = game_connection.handle_action('PlayerOption', [1, 'Sheeo', 'Color', 2])
    loop.run_until_complete(result)
    # Shouldn't raise an exception


def test_handle_action_GameOption(game, loop, game_connection):
    result = asyncio.async(game_connection.handle_action('PlayerOption', [1, 'Color', 2]))
    loop.run_until_complete(result)
    game.set_player_option.assert_called_once_with(1, 'Color', 2)


def test_handle_action_GameResult_calls_add_result(game, loop, game_connection):
    result = asyncio.async(game_connection.handle_action('GameResult', [0, 'score -5']))
    loop.run_until_complete(result)
    game.add_result.assert_called_once_with(game_connection.player, 0, 'score', -5)


def test_on_connection_lost_proxy_cleanup(game_connection, players):
    game_connection.game = mock.Mock()
    game_connection.game.proxy = mock.Mock()
    game_connection.game.proxy.unmap.return_value = True
    game_connection.player = players.hosting
    game_connection.connectivity_state.set_result(Connectivity.PROXY)

    with mock.patch('server.gameconnection.socket') as socket:
        game_connection.on_connection_lost()

        socket.socket().sendall.assert_called_with(ujson.dumps(dict(command='cleanup', sourceip=players.hosting.ip)).encode())



@asyncio.coroutine
def test_ConnectToHost_public_public(connections, players):
    host_conn = connections.make_connection(players.hosting, Connectivity.PUBLIC)
    peer_conn = connections.make_connection(players.joining, Connectivity.PUBLIC)
    host_conn.send_ConnectToPeer = mock.Mock()
    peer_conn.send_JoinGame = mock.Mock()
    yield from peer_conn.ConnectToHost(host_conn)
    host_conn.send_ConnectToPeer.assert_called_with(peer_conn.player.address_and_port,
                                                    peer_conn.player.login,
                                                    peer_conn.player.id)
    peer_conn.send_JoinGame.assert_called_with(host_conn.player.address_and_port,
                                               False,
                                               host_conn.player.login,
                                               host_conn.player.id)

@asyncio.coroutine
def test_ConnectToHost_public_stun(connections, players):
    host_conn = connections.make_connection(players.hosting, Connectivity.PUBLIC)
    peer_conn = connections.make_connection(players.joining, Connectivity.STUN)
    host_conn.send_ConnectToPeer = mock.Mock()
    peer_conn.send_SendNatPacket = mock.Mock()
    peer_conn.send_JoinGame = mock.Mock()
    result = asyncio.async(peer_conn.ConnectToHost(host_conn))
    yield from asyncio.sleep(0.05)
    host_conn.notify({'command_id': 'ProcessNatPacket',
                      'arguments': [peer_conn.player.address_and_port,
                                    "Hello {}".format(host_conn.player.id)]})
    yield from result
    peer_conn.send_SendNatPacket.assert_called_with(host_conn.player.address_and_port,
                                                    "Hello {}".format(host_conn.player.id))
    host_conn.send_ConnectToPeer.assert_called_with(peer_conn.player.address_and_port,
                                                    peer_conn.player.login,
                                                    peer_conn.player.id)
    peer_conn.send_JoinGame.assert_called_with(host_conn.player.address_and_port,
                                               False,
                                               host_conn.player.login,
                                               host_conn.player.id)

@asyncio.coroutine
def test_ConnectToHost_stun_public(connections, players):
    host_conn = connections.make_connection(players.hosting, Connectivity.STUN)
    peer_conn = connections.make_connection(players.joining, Connectivity.PUBLIC)
    host_conn.send_ConnectToPeer = mock.Mock()
    host_conn.send_SendNatPacket = mock.Mock()
    peer_conn.send_JoinGame = mock.Mock()
    result = asyncio.async(peer_conn.ConnectToHost(host_conn))
    yield from asyncio.sleep(0.05)
    peer_conn.notify({'command_id': 'ProcessNatPacket',
                      'arguments': [peer_conn.player.address_and_port,
                                    "Hello {}".format(peer_conn.player.id)]})
    yield from result
    host_conn.send_SendNatPacket.assert_called_with(peer_conn.player.address_and_port,
                                                    "Hello {}".format(peer_conn.player.id))
    host_conn.send_ConnectToPeer.assert_called_with(peer_conn.player.address_and_port,
                                                   peer_conn.player.login,
                                                   peer_conn.player.id)
    peer_conn.send_JoinGame.assert_called_with(host_conn.player.address_and_port,
                                               False,
                                               host_conn.player.login,
                                               host_conn.player.id)

@asyncio.coroutine
def test_ConnectToHost_public_proxy(connections, players):
    host_conn = connections.make_connection(players.hosting, Connectivity.PUBLIC)
    peer_conn = connections.make_connection(players.joining, Connectivity.PROXY)
    host_conn.send_ConnectToProxy = mock.Mock()
    peer_conn.send_ConnectToProxy = mock.Mock()
    host_conn.game.proxy = proxy_map.ProxyMap()
    result = asyncio.async(peer_conn.ConnectToHost(host_conn))
    yield from result
    host_conn.send_ConnectToProxy.assert_called_with(0,
                                                     peer_conn.player.ip,
                                                     peer_conn.player.login,
                                                     peer_conn.player.id)
    peer_conn.send_ConnectToProxy.assert_called_with(0,
                                                     host_conn.player.ip,
                                                     host_conn.player.login,
                                                     host_conn.player.id)

@asyncio.coroutine
def test_ConnectToPeer_(loop):
    pass
