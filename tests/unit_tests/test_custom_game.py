import logging
from unittest import mock
import asyncio

import pytest
import time

from server import GameStatsService
from server.games.game import GameState, ValidityState
from server.games.custom_game import CustomGame
from server.gameconnection import GameConnection, GameConnectionState
from server.players import Player
from tests import CoroMock


@pytest.fixture()
def game_stats_service():
    service = mock.Mock(spec=GameStatsService)
    service.process_game_stats = CoroMock()
    return service

@pytest.fixture()
def game_connection(state=GameConnectionState.INITIALIZING, player=None):
    gc = mock.create_autospec(spec=GameConnection)
    gc.state = state
    gc.player = player
    return gc

def add_connected_player(custom_game: CustomGame, player):
    custom_game.game_service.player_service[player.id] = player
    gc = game_connection(state=GameConnectionState.CONNECTED_TO_HOST, player=player)
    custom_game.set_player_option(player.id, 'Army', 0)
    custom_game.set_player_option(player.id, 'StartSpot', 0)
    custom_game.set_player_option(player.id, 'Team', 0)
    custom_game.set_player_option(player.id, 'Faction', 0)
    custom_game.set_player_option(player.id, 'Color', 0)
    custom_game.add_game_connection(gc)
    return gc

def add_connected_players(game: CustomGame, players):
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

async def test_rate_game_early_abort_no_enforce(game_service, game_stats_service):
    custom_game = CustomGame(50, game_service, game_stats_service)
    custom_game.state = GameState.LOBBY
    players = [
        Player(id=1, login='Dostya', global_rating=(1500, 500)),
        Player(id=2, login='Rhiza', global_rating=(1500, 500)),
    ]
    add_connected_players(custom_game, players)
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
    await custom_game.launch()
    await custom_game.add_result(0, 1, 'VICTORY', 5)

    custom_game.launched_at = time.time() - 600 # seconds

    await custom_game.on_game_end()
    assert custom_game.validity == ValidityState.VALID