from unittest import mock

import pytest

from server.gameconnection import GameConnection
from server.lobbyconnection import LobbyConnection



@pytest.fixture()
def lobbythread():
    return mock.Mock(
        sendJSON=lambda obj: None
    )


@pytest.fixture
def game_connection(game, loop, player_service, players, games, transport, connected_game_socket):
    conn = GameConnection(loop=loop, users=player_service, games=games, db=None, server=None)
    conn._socket = connected_game_socket
    conn.transport = transport
    conn.player = players.hosting
    conn.game = game
    game_connection.lobby = mock.Mock(spec=LobbyConnection)
    return conn


@pytest.fixture
def connections(loop, player_service, games, transport, game):
    def make_connection(player, connectivity):
        conn = GameConnection(loop=loop, users=player_service, games=games, db=None, server=None)
        conn.player = player
        conn.game = game
        conn.transport = transport
        conn.connectivity_state.set_result(connectivity)
        return conn

    return mock.Mock(
        make_connection=make_connection
    )
