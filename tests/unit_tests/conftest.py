from unittest import mock
import pytest

from server import GameStatsService, LobbyConnection
from server.abc.base_game import BaseGame
from server.games import Game
from server.gameconnection import GameConnection, GameConnectionState
from server.players import Player
from tests import CoroMock

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
def mock_game_connection(state=GameConnectionState.INITIALIZING, player=None):
    gc = mock.create_autospec(spec=GameConnection)
    gc.state = state
    gc.player = player
    return gc


@pytest.fixture()
def game_stats_service():
    service = mock.Mock(spec=GameStatsService)
    service.process_game_stats = CoroMock()
    return service


@pytest.fixture
def connections(loop, player_service, game_service, transport, game):
    from server import GameConnection

    def make_connection(player, connectivity):
        lc = LobbyConnection(loop)
        lc.protocol = mock.Mock()
        conn = GameConnection(loop=loop,
                              lobby_connection=lc,
                              player_service=player_service,
                              games=game_service)
        conn.player = player
        conn.game = game
        conn._transport = transport
        conn._connectivity_state.set_result(connectivity)
        return conn

    return mock.Mock(
        make_connection=make_connection
    )

def add_connected_player(game: Game, player):
    game.game_service.player_service[player.id] = player
    gc = mock_game_connection(state=GameConnectionState.CONNECTED_TO_HOST, player=player)
    game.set_player_option(player.id, 'Army', 0)
    game.set_player_option(player.id, 'StartSpot', 0)
    game.set_player_option(player.id, 'Team', 0)
    game.set_player_option(player.id, 'Faction', 0)
    game.set_player_option(player.id, 'Color', 0)
    game.add_game_connection(gc)
    return gc


def add_connected_players(game: BaseGame, players):
    """
    Utility to add players with army and StartSpot indexed by a list
    """
    for army, player in enumerate(players):
        add_connected_player(game, player)
        game.set_player_option(player.id, 'Army', army)
        game.set_player_option(player.id, 'StartSpot', army)
        game.set_player_option(player.id, 'Team', army)
        game.set_player_option(player.id, 'Faction', 0)
        game.set_player_option(player.id, 'Color', 0)
    game.host = players[0]

def add_players(gameobj: BaseGame, n: int):
    game = gameobj
    current = len(game.players)
    players = []
    for i in range(current, current+n):
        players.append(Player(id=i+1, login='Player '+str(i+1), global_rating=(1500, 500)))

    add_connected_players(game, players)
    return players
