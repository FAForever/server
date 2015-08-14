import asyncio
from unittest import mock

import pytest

@pytest.fixture()
def lobbythread():
    return mock.Mock(
        sendJSON=lambda obj: None
    )


@pytest.fixture
def game_connection(request, game, loop, player_service, players, game_service, transport, connected_game_socket):
    from server import GameConnection, LobbyConnection
    conn = GameConnection(loop=loop, users=player_service, games=game_service)
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
def connections(loop, player_service, game_service, transport, game):
    from server import GameConnection
    def make_connection(player, connectivity):
        conn = GameConnection(loop=loop, users=player_service, games=game_service)
        conn.protocol = mock.Mock()
        conn.player = player
        conn.game = game
        conn._transport = transport
        conn._connectivity_state.set_result(connectivity)
        return conn

    return mock.Mock(
        make_connection=make_connection
    )
