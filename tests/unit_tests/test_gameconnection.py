import asyncio

from PySide.QtNetwork import QTcpSocket
import mock

from src import proxy_map
from src.connectivity import Connectivity
from src.gameconnection import GameConnection
from src.JsonTransport import Transport
from src.games import Game


def test_accepts_valid_socket(game_connection, connected_game_socket):
    """
    :type game_connection: GameConnection
    :type connected_game_socket QTcpSocket
    """
    assert game_connection.accept(connected_game_socket) is True


def test_accept_no_player_aborts(game_connection, connected_game_socket):
    mock_users = mock.Mock()
    mock_users.findByIp = mock.Mock(return_value=None)
    game_connection.users = mock_users
    game_connection.accept(connected_game_socket)
    connected_game_socket.abort.assert_any_call()


def test_test_doEnd(game_connection, game):
    game_connection.doEnd()
    game.remove_game_connection.assert_called_with(game_connection)


@asyncio.coroutine
def test_ping_miss(game_connection):
    game_connection.abort = mock.Mock()
    game_connection.last_pong = 0
    asyncio.async(game_connection.ping())
    yield from asyncio.sleep(0.1)
    game_connection.abort.assert_any_call()

@asyncio.coroutine
def test_ping_hit(game_connection, transport):
    game_connection.abort = mock.Mock()
    asyncio.async(game_connection.ping())
    yield from asyncio.sleep(0.1)
    transport.send_message.assert_any_call({
        'key': 'ping',
        'commands': []
    })
    for i in range(1, 3):
        game_connection.handle_action('pong', [])
        game_connection.ping()
    assert game_connection.abort.mock_calls == []

def test_abort(game_connection, players, connected_game_socket):
    game_connection.player = players.hosting
    game_connection.socket = connected_game_socket
    game_connection.abort()
    connected_game_socket.abort.assert_any_call()
    players.hosting.lobbyThread.sendJSON.assert_called_with(
        dict(command='notice',
             style='kill')
    )

@asyncio.coroutine
def test_handle_action_GameState_idle_adds_connection(game_connection, players, game):
    game_connection.player = players.joining
    yield from game_connection.handle_action('GameState', ['Idle'])
    game.add_game_connection.assert_called_with(game_connection)

@asyncio.coroutine
def test_handle_action_GameState_idle_as_peer_sends_CreateLobby(game_connection, players, games, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    game_connection.player = players.joining
    yield from game_connection.handle_action('GameState', ['Idle'])
    games.find_by_id.assert_called_once_with(players.joining.getGame())
    transport.send_message.assert_any_call({'key': 'CreateLobby',
                                            'commands': [0, players.joining.gamePort,
                                                         players.joining.login,
                                                         players.joining.id,
                                                         1]})

@asyncio.coroutine
def test_handle_action_GameState_idle_as_host_sends_CreateLobby(game_connection, players, games, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    game_connection.player = players.hosting
    yield from game_connection.handle_action('GameState', ['Idle'])
    games.find_by_id.assert_called_once_with(players.hosting.getGame())
    transport.send_message.assert_any_call({'key': 'CreateLobby',
                                            'commands': [0, players.hosting.gamePort,
                                                         players.hosting.login,
                                                         players.hosting.id,
                                                         1]})


def test_handle_action_GameState_lobby_sends_HostGame(game_connection, loop, patch_connectivity, players, game, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    game_connection.player = players.hosting
    game.mapName = 'some_map'
    result = asyncio.async(game_connection.handle_action('GameState', ['Lobby']))
    loop.run_until_complete(result)
    transport.send_message.assert_any_call({'key': 'HostGame', 'commands': [game.mapName]})


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
