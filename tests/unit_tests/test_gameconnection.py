import asyncio

from PySide.QtNetwork import QTcpSocket
import mock
import pytest
from src.connectivity import Connectivity

from src.gameconnection import GameConnection
from src.JsonTransport import Transport
from games import Game




def test_accepts_valid_socket(game_connection, loop, connected_game_socket):
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
    game_connection.player = players.hosting
    result = asyncio.async(game_connection.handle_action('GameState', ['Lobby']))
    loop.run_until_complete(result)
    transport.send_message.assert_any_call({'key': 'HostGame', 'commands': [str(game.getMapName())]})

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

def test_ConnectToHost_public_public(loop, connections, players):
    host_conn = connections.make_connection(players.hosting, Connectivity.PUBLIC)
    peer_conn = connections.make_connection(players.joining, Connectivity.PUBLIC)
    host_conn.send_ConnectToPeer = mock.Mock()
    peer_conn.send_JoinGame = mock.Mock()
    host = players.hosting
    peer = players.joining
    @asyncio.coroutine
    def test():
        yield from host_conn.ConnectToHost(peer_conn)
        host_conn.send_ConnectToPeer.assert_called_with(peer.address_and_port, peer.login, peer.id)
        peer_conn.send_JoinGame.assert_called_with(host.address_and_port,
                                                   False,
                                                   host.getLogin(),
                                                   host.getId())
    loop.run_until_complete(asyncio.wait_for(test(), 2))

