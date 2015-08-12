import asyncio
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
def game_connection(request, game, loop, player_service, players, games, transport, connected_game_socket):
    conn = GameConnection(loop=loop, users=player_service, games=games, db=None)
    conn._transport = transport
    conn.player = players.hosting
    conn.game = game
    conn.lobby = mock.Mock(spec=LobbyConnection)
    conn._authenticated = asyncio.Future()
    conn._authenticated.set_result(42)
    def fin():
        conn.abort()
    request.addfinalizer(fin)
    return conn


@pytest.fixture
def connections(loop, player_service, games, transport, game):
    def make_connection(player, connectivity):
        conn = GameConnection(loop=loop, users=player_service, games=games, db=None)
        conn.protocol = mock.Mock()
        conn.player = player
        conn.game = game
        conn._transport = transport
        conn._connectivity_state.set_result(connectivity)
        return conn

    return mock.Mock(
        make_connection=make_connection
    )
