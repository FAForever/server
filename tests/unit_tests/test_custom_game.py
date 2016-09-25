from unittest import mock

import pytest
import time

from server.games.game import GameState, ValidityState
from server.games import CustomGame
from server.players import Player
from tests.unit_tests.conftest import add_connected_players


async def test_rate_game_early_abort_no_enforce(game_service, game_stats_service):
    custom_game = CustomGame(50, game_service, game_stats_service)
    custom_game.state = GameState.LOBBY
    players = [
        Player(id=1, login='Dostya', global_rating=(1500, 500)),
        Player(id=2, login='Rhiza', global_rating=(1500, 500)),
    ]
    add_connected_players(custom_game, players)
    custom_game.set_player_option(1, 'Team', 2)
    custom_game.set_player_option(2, 'Team', 3)
    await custom_game.launch()
    await custom_game.add_result(0, 1, 'VICTORY', 5)

    custom_game.launched_at = time.time() - 60 # seconds

    await custom_game.on_game_end()
    assert custom_game.validity == ValidityState.TOO_SHORT

async def test_rate_game_early_abort_with_enforce(game_service, game_stats_service):
    custom_game = CustomGame(51, game_service, game_stats_service)
    custom_game.state = GameState.LOBBY
    players = [
        Player(id=1, login='Dostya', global_rating=(1500, 500)),
        Player(id=2, login='Rhiza', global_rating=(1500, 500)),
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


async def test_rate_game_late_abort_no_enforce(game_service, game_stats_service):
    custom_game = CustomGame(45, game_service, game_stats_service)
    custom_game.state = GameState.LOBBY
    players = [
        Player(id=1, login='Dostya', global_rating=(1500, 500)),
        Player(id=2, login='Rhiza', global_rating=(1500, 500)),
    ]
    add_connected_players(custom_game, players)
    custom_game.set_player_option(1, 'Team', 2)
    custom_game.set_player_option(2, 'Team', 3)
    await custom_game.launch()
    await custom_game.add_result(0, 1, 'VICTORY', 5)

    custom_game.launched_at = time.time() - 600 # seconds

    await custom_game.on_game_end()
    assert custom_game.validity == ValidityState.VALID