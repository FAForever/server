from unittest import mock
import pytest

from games.game import Game, GameState, GameError
from src.gameconnection import GameConnection, GameConnectionState


@pytest.fixture()
def game():
    return Game(42)


def test_initialization(game):
    assert game.state == GameState.INITIALIZING

@pytest.fixture(params=[
    [('PlayerName', 'Sheeo'),
     ('StartSpot', 0)]
])
def player_option(request):
    return request.param

@pytest.fixture
def game_connection():
    return mock.create_autospec(spec=GameConnection)


def test_add_game_connection(game: Game, players, game_connection):
    game.state = GameState.LOBBY
    game_connection.player = players.hosting
    game_connection.state = GameConnectionState.connected_to_host
    game.add_game_connection(game_connection)
    assert players.hosting in game.players


def test_add_game_connection_throws_if_not_connected_to_host(game: Game, players, game_connection):
    game.state = GameState.LOBBY
    game_connection.player = players.hosting
    game_connection.state = GameConnectionState.initialized
    with pytest.raises(GameError):
        game.add_game_connection(game_connection)

    assert players.hosting not in game.players


def test_remove_game_connection(game: Game, players, game_connection):
    game.state = GameState.LOBBY
    game_connection.player = players.hosting
    game_connection.state = GameConnectionState.connected_to_host
    game.add_game_connection(game_connection)
    game.remove_game_connection(game_connection)
    assert players.hosting not in game.players


