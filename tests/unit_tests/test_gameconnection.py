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


@asyncio.coroutine
def test_handle_action_GameState_idle_sends_CreateLobby(game_connection, players, games, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    game_connection.player = players.joining
    yield from game_connection.handle_action('GameState', ['Idle'])
    games.getGameByUuid.assert_called_once_with(players.joining.getGame())
    transport.send_message.assert_any_call({'key': 'CreateLobby',
                                            'commands': [0, players.joining.getGamePort(),
                                                         players.joining.getLogin(),
                                                         players.joining.id,
                                                         1]})

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


@asyncio.coroutine
def test_ConnectToHost_public_public(connections, players):
    host_conn = connections.make_connection(players.hosting, Connectivity.PUBLIC)
    peer_conn = connections.make_connection(players.joining, Connectivity.PUBLIC)
    host_conn.send_ConnectToPeer = mock.Mock()
    peer_conn.send_JoinGame = mock.Mock()
    yield from host_conn.ConnectToHost(peer_conn)
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
    result = asyncio.async(host_conn.ConnectToHost(peer_conn))
    yield from asyncio.sleep(0.01)
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
    result = asyncio.async(host_conn.ConnectToHost(peer_conn))
    yield from asyncio.sleep(0.01)
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

