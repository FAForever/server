import pytest

from games.game import Game, GameState

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

def test_PlayerOption(game, player_option):
    game.setPlayerOption(1, player_option[0], player_option[1])
    assert game.getPlayerOption(1, player_option[0]) == player_option[1]

