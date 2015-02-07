import asyncio
import pytest
import mock

from PySide.QtNetwork import QTcpSocket
from FaServerThread import FAServerThread

from gameconnection import GameConnection
from JsonTransport import Transport
from games import Game


@pytest.fixture
def game_connection(game, patch_config, loop, player_service, players, games, transport, monkeypatch, connected_game_socket):
    conn = GameConnection(loop=loop, users=player_service, games=games, db=None, parent=None)
    conn.socket = connected_game_socket
    conn.transport = transport
    conn.player = players.hosting
    conn.game = game
    game_connection.lobby = mock.Mock(spec=FAServerThread)
    return conn

def test_accepts_valid_socket(game_connection, connected_game_socket):
    """
    :type game_connection: GameConnection
    :type connected_game_socket QTcpSocket
    """
    assert game_connection.accept(connected_game_socket) is True


def test_handle_action_GameState_idle_sends_CreateLobby(game_connection, loop, players, games, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    game_connection.player = players.joining
    result = asyncio.async(game_connection.handle_action('GameState', ['Idle']))
    loop.run_until_complete(result)
    games.getGameByUuid.assert_called_once_with(players.joining.getGame())
    transport.send_message.assert_any_call({'key': 'CreateLobby',
                                            'commands': [0, players.joining.getGamePort(),
                                                         players.joining.getLogin(), 2, 1]})

def test_handle_action_GameState_lobby_sends_HostGame(game_connection, loop, patch_connectivity, players, game, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    #patch_connectivity(Connectivity.PUBLIC)
    game_connection.player = players.hosting
    result = asyncio.async(game_connection.handle_action('GameState', ['Lobby']))
    loop.run_until_complete(result)
    transport.send_message.assert_any_call({'key': 'HostGame', 'commands': [str(game.getMapName())]})

def test_handle_action_GameState_lobby_sends_JoinGame(game_connection, loop, patch_connectivity, players, game, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    #patch_connectivity(Connectivity.PUBLIC)
    game_connection.player = players.joining
    result = asyncio.async(game_connection.handle_action('GameState', ['Lobby']))
    loop.run_until_complete(result)
    transport.send_message.assert_any_call({'key': 'JoinGame', 'commands': [
        str(game.getHostIp()),
        str(game.getHostName()),
        int(game.getHostId())
    ]})
    game.add_peer.assert_called_with(players.joining, game_connection)

def test_handle_action_ConnectedToHost(game, loop, game_connection, players):
    """
    :type game Game
    :type game_connection GameConnection
    """
    game_connection.player = players.joining
    loop.run_until_complete(asyncio.async(game_connection.handle_action('ConnectedToHost', [])))
    game.add_connection.assert_called_once_with(players.joining, players.hosting)

def test_handle_action_PlayerOption(game, loop, game_connection):
    """
    :type game Game
    :type game_connection GameConnection
    """
    result = asyncio.async(game_connection.handle_action('PlayerOption', [1, 'Color', 2]))
    loop.run_until_complete(result)
    game.setPlayerOption.assert_called_once_with(1, 'Color', 2)


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
    game.setPlayerOption.assert_called_once_with(1, 'Color', 2)

