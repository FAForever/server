import asyncio
from unittest import mock
import pytest

from server import LobbyConnection


@pytest.fixture()
def lobbythread():
    return mock.Mock(
        sendJSON=lambda obj: None
    )


@pytest.fixture
def game_connection(request, game, loop, player_service, players, game_service, transport):
    from server import GameConnection, LobbyConnection
    conn = GameConnection(loop=loop,
                          lobby_connection=mock.create_autospec(LobbyConnection(loop)),
                          player_service=player_service,
                          games=game_service)
    conn._transport = transport
    conn.player = players.hosting
    conn.game = game
    conn.lobby = mock.Mock(spec=LobbyConnection)

    def fin():
        conn.abort()

    request.addfinalizer(fin)
    return conn


@pytest.fixture
def connections(loop, player_service, game_service, transport, game):
    from server import GameConnection

    def make_connection(player, connectivity):
        lc = LobbyConnection(loop)
        conn = GameConnection(loop=loop,
                              lobby_connection=lc,
                              player_service=player_service,
                              games=game_service)
        conn.protocol = mock.Mock()
        conn.player = player
        conn.game = game
        conn._transport = transport
        conn._connectivity_state.set_result(connectivity)
        return conn

    return mock.Mock(
        make_connection=make_connection
    )
