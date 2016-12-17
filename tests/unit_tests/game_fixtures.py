import pytest
from server.games.game import Game
from server.games.custom_game import CustomGame

@pytest.yield_fixture
def game(loop, game_service, game_stats_service):
    game = Game(42, game_service, game_stats_service)
    yield game
    loop.run_until_complete(game.clear_data())

@pytest.yield_fixture
def custom_game(loop, game_service, game_stats_service):
    game = CustomGame(42, game_service, game_stats_service)
    yield game
    loop.run_until_complete(game.clear_data())

