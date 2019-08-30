import pytest
import time

from server.games import CustomGame
from server.games.game import GameState, ValidityState
from tests.unit_tests.conftest import add_connected_players
from server.rating import RatingType

pytestmark = pytest.mark.asyncio


@pytest.yield_fixture
def custom_game(loop, database, game_service, game_stats_service):
    game = CustomGame(42, database, game_service, game_stats_service)
    yield game
    loop.run_until_complete(game.clear_data())


async def test_rate_game_early_abort_no_enforce(
        game_service, game_stats_service, custom_game, player_factory):
    custom_game.state = GameState.LOBBY
    players = [
        player_factory(player_id=1, login='Dostya', global_rating=(1500, 500)),
        player_factory(player_id=2, login='Rhiza', global_rating=(1500, 500)),
    ]
    add_connected_players(custom_game, players)
    custom_game.set_player_option(1, 'Team', 2)
    custom_game.set_player_option(2, 'Team', 3)
    await custom_game.launch()
    await custom_game.add_result(0, 1, 'VICTORY', 5)

    custom_game.launched_at = time.time() - 60  # seconds

    await custom_game.on_game_end()
    assert custom_game.validity == ValidityState.TOO_SHORT


async def test_rate_game_early_abort_with_enforce(
        game_service, game_stats_service, custom_game, player_factory):
    custom_game.state = GameState.LOBBY
    players = [
        player_factory(player_id=1, login='Dostya', global_rating=(1500, 500)),
        player_factory(player_id=2, login='Rhiza', global_rating=(1500, 500)),
    ]
    add_connected_players(custom_game, players)
    custom_game.set_player_option(1, 'Team', 2)
    custom_game.set_player_option(2, 'Team', 3)
    await custom_game.launch()
    custom_game.enforce_rating = True
    await custom_game.add_result(0, 1, 'VICTORY', 5)

    custom_game.launched_at = time.time() - 60  # seconds

    await custom_game.on_game_end()
    assert custom_game.validity == ValidityState.VALID


async def test_rate_game_late_abort_no_enforce(
        game_service, game_stats_service, custom_game, player_factory):
    custom_game.state = GameState.LOBBY
    players = [
        player_factory(player_id=1, login='Dostya', global_rating=(1500, 500)),
        player_factory(player_id=2, login='Rhiza', global_rating=(1500, 500)),
    ]
    add_connected_players(custom_game, players)
    custom_game.set_player_option(1, 'Team', 2)
    custom_game.set_player_option(2, 'Team', 3)
    await custom_game.launch()
    await custom_game.add_result(0, 1, 'VICTORY', 5)

    custom_game.launched_at = time.time() - 600     # seconds

    await custom_game.on_game_end()
    assert custom_game.validity == ValidityState.VALID


async def test_global_rating_higher_after_custom_game_win(
        custom_game: CustomGame, game_add_players):
    game = custom_game
    game.state = GameState.LOBBY
    players = game_add_players(game, 2)
    game.set_player_option(players[0].id, 'Team', 1)
    game.set_player_option(players[1].id, 'Team', 2)
    old_mean = players[0].ratings[RatingType.GLOBAL][0]

    await game.launch()
    game.launched_at = time.time() - 60*20  # seconds
    await game.add_result(0, 0, 'victory', 5)
    await game.add_result(0, 1, 'defeat', -5)
    await game.on_game_end()

    assert game.validity is ValidityState.VALID
    assert players[0].ratings[RatingType.GLOBAL][0] > old_mean
