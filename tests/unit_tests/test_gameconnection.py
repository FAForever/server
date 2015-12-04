import asyncio
import json

from unittest import mock

from server import GameConnection
from server.connectivity import ConnectivityResult, ConnectivityState
from server.games import Game
from server.players import PlayerState

LOCAL_PUBLIC = ConnectivityResult(addr='127.0.0.1:6112', state=ConnectivityState.PUBLIC)
LOCAL_STUN = ConnectivityResult(addr='127.0.0.1:6112', state=ConnectivityState.STUN)
LOCAL_PROXY = ConnectivityResult(addr=None, state=ConnectivityState.BLOCKED)

def assert_message_sent(game_connection, command, args):
    game_connection.lobby_connection.send.assert_called_with({
        'command': command,
        'target': 'game',
        'args': args
    })

def test_abort(game_connection, game, players):
    game_connection.player = players.hosting
    game_connection.game = game

    game_connection.abort()

    game.remove_game_connection.assert_called_with(game_connection)

@asyncio.coroutine
def test_handle_action_GameState_idle_adds_connection(game_connection, players, game):
    players.joining.game = game
    game_connection.lobby_connection = mock.Mock()
    game_connection.player = players.hosting
    game_connection.game = game

    yield from game_connection.handle_action('GameState', ['Idle'])

    game.add_game_connection.assert_called_with(game_connection)

@asyncio.coroutine
def test_handle_action_GameState_idle_non_searching_player_aborts(game_connection, players):
    game_connection.player = players.hosting
    game_connection.lobby = mock.Mock()
    game_connection.abort = mock.Mock()
    players.hosting.state = PlayerState.IDLE

    yield from game_connection.handle_action('GameState', ['Idle'])

    game_connection.abort.assert_any_call()


def test_handle_action_GameState_lobby_sends_HostGame(game_connection, loop, players, game):
    """
    :type game_connection: GameConnection
    """
    game_connection.player = players.hosting
    game.map_file_path = 'some_map'

    result = asyncio.async(game_connection.handle_action('GameState', ['Lobby']))
    loop.run_until_complete(result)

    assert_message_sent(game_connection, 'HostGame', [game.map_file_path])


def test_handle_action_GameState_lobby_calls_ConnectToHost(game_connection, loop, players, game):
    """
    :type game_connection: GameConnection
    """
    game_connection.send_message = mock.MagicMock()
    game_connection.ConnectToHost = mock.Mock()
    game_connection.player = players.joining
    players.joining.game = game
    game.host = players.hosting
    game.map_file_path = 'some_map'

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

async def test_ConnectToHost_public_public(connections, players):
    host_conn = connections.make_connection(players.hosting, LOCAL_PUBLIC)
    peer_conn = connections.make_connection(players.joining, LOCAL_PUBLIC)
    host_conn.send_ConnectToPeer = mock.Mock()
    peer_conn.send_JoinGame = mock.Mock()
    await peer_conn.ConnectToHost(host_conn)
    host_conn.send_ConnectToPeer.assert_called_with(peer_conn.player.address_and_port,
                                                    peer_conn.player.login,
                                                    peer_conn.player.id)
    peer_conn.send_JoinGame.assert_called_with(host_conn.player.address_and_port,
                                               host_conn.player.login,
                                               host_conn.player.id)

async def test_json_stats(game_connection, game_stats_service, players, game):
    game_stats_service.process_game_stats = mock.Mock()
    await game_connection.handle_action('JsonStats', ['{"stats": {}}'])
    game.report_army_stats.assert_called_once_with('{"stats": {}}')
