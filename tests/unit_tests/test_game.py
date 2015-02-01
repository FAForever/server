import pytest

from games.game import Game, GameState

@pytest.fixture()
def game():
    return Game(42)


def test_initialization(game):
    assert game.state == GameState.INITIALIZING


def test_slots(game):
    game.setPlayerOption(1, "PlayerName", 'Sheeo')
    game.setPlayerOption(1, "StartSpot", 2)
    assert game.getPlayerOption(2, "PlayerName") == 'Sheeo'

