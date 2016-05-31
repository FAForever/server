import logging
from unittest import mock
from mock import patch

import pytest
import time

from trueskill import Rating

from server.games.game import Game, GameState, GameError, VisibilityState
from server.gameconnection import GameConnection, GameConnectionState
from server.players import Player
from tests import CoroMock
from tests.unit_tests.conftest import mock_game_connection, add_connected_players, add_connected_player


@pytest.fixture()
def game(game_service, game_stats_service):
    return Game(42, game_service, game_stats_service)


def test_initialization(game: Game):
    assert game.state == GameState.INITIALIZING
    assert game.enforce_rating == False


def test_instance_logging(game_stats_service):
    logger = logging.getLogger('{}.5'.format(Game.__qualname__))
    logger.info = mock.Mock()
    mock_parent = mock.Mock()
    game = Game(5, mock_parent, game_stats_service)
    logger.info.assert_called_with("{} created".format(game))


def test_set_player_option(game, players, mock_game_connection):
    game.state = GameState.LOBBY
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(mock_game_connection)
    assert game.players == {players.hosting}
    game.set_player_option(players.hosting.id, 'Team', 1)
    assert game.get_player_option(players.hosting.id, 'Team') == 1
    assert game.teams == {1}
    game.set_player_option(players.hosting.id, 'StartSpot', 1)
    game.get_player_option(players.hosting.id, 'StartSpot') == 1


def test_add_game_connection(game: Game, players, mock_game_connection):
    game.state = GameState.LOBBY
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(mock_game_connection)
    assert players.hosting in game.players


def test_add_game_connection_throws_if_not_connected_to_host(game: Game, players, mock_game_connection):
    game.state = GameState.LOBBY
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.INITIALIZED
    with pytest.raises(GameError):
        game.add_game_connection(mock_game_connection)

    assert players.hosting not in game.players


def test_add_game_connection_throws_if_not_lobby_state(game: Game, players, mock_game_connection):
    game.state = GameState.INITIALIZING
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    with pytest.raises(GameError):
        game.add_game_connection(mock_game_connection)

    assert players.hosting not in game.players


async def test_remove_game_connection(game: Game, players, mock_game_connection):
    game.state = GameState.LOBBY
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(mock_game_connection)
    await game.remove_game_connection(mock_game_connection)
    assert players.hosting not in game.players


async def test_game_end_when_no_more_connections(game: Game, mock_game_connection):
    game.state = GameState.LOBBY

    game.on_game_end = CoroMock()
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(mock_game_connection)
    await game.remove_game_connection(mock_game_connection)

    game.on_game_end.assert_any_call()

@patch('asyncio.sleep', return_value=None)
async def test_game_marked_dirty_when_timed_out(game: Game):
    game.state = GameState.INITIALIZING
    await game.timeout_game()
    assert game.state == GameState.ENDED
    assert game in game.game_service.dirty_games

async def test_clear_slot(game: Game, mock_game_connection: GameConnection):
    game.state = GameState.LOBBY
    players = [
        Player(id=1, login='Dostya', global_rating=(1500, 500)),
        Player(id=2, login='Rhiza', global_rating=(1500, 500))
    ]
    add_connected_players(game, players)

    game.clear_slot(0)

    assert game.get_player_option(1, 'StartSpot') == -1
    assert game.get_player_option(1, 'Team') == -1
    assert game.get_player_option(1, 'Army') == -1
    assert game.get_player_option(2, 'StartSpot') == 1

async def test_game_launch_freezes_players(game: Game, players):
    await game.clear_data()
    game.state = GameState.LOBBY
    host_conn = add_connected_player(game, players.hosting)
    game.host = players.hosting
    add_connected_player(game, players.joining)

    await game.launch()

    assert game.state == GameState.LIVE
    assert game.players == {players.hosting, players.joining}

    await game.remove_game_connection(host_conn)
    assert game.players == {players.hosting, players.joining}


def test_game_teams_represents_active_teams(game: Game, players):
    game.state = GameState.LOBBY
    add_connected_players(game, [players.hosting, players.joining])
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 2)
    assert game.teams == {1, 2}


async def test_compute_rating_computes_global_ratings(game: Game, players):
    await game.clear_data()

    game.state = GameState.LOBBY
    players.hosting.global_rating = Rating(1500, 250)
    players.joining.global_rating = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    await game.add_result(players.hosting, 0, 'victory', 1)
    await game.add_result(players.joining, 1, 'defeat', 0)
    game.set_player_option(players.hosting.id, 'Team', 2)
    game.set_player_option(players.joining.id, 'Team', 3)
    groups = game.compute_rating()
    assert players.hosting in groups[0]
    assert players.joining in groups[1]


async def test_compute_rating_computes_ladder_ratings(game: Game, players):
    await game.clear_data()

    game.state = GameState.LOBBY
    players.hosting.ladder_rating = Rating(1500, 250)
    players.joining.ladder_rating = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    await game.add_result(players.hosting, 0, 'victory', 1)
    await game.add_result(players.joining, 1, 'defeat', 0)
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 1)
    groups = game.compute_rating(rating='ladder')
    assert players.hosting in groups[0]
    assert players.joining in groups[1]


async def test_compute_rating_balanced_teamgame(game: Game, create_player):
    await game.clear_data()

    game.state = GameState.LOBBY
    players = [
        (create_player(**info), result, team) for info, result, team in [
            (dict(login='Paula_Bean', id=1, global_rating=Rating(1500, 250.7)), 0, 1),
            (dict(login='Some_Guy', id=2, global_rating=Rating(1700, 120.1)), 0, 1),
            (dict(login='Some_Other_Guy', id=3, global_rating=Rating(1200, 72.02)), 0, 2),
            (dict(login='That_Person', id=4, global_rating=Rating(1200, 72.02)), 0, 2),
        ]
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()
    for player, result, _ in players:
        await game.add_result(player, player.id - 1, 'score', result)
    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert player in game.players
            assert new_rating != Rating(*player.global_rating)


async def test_on_game_end_calls_rate_game(game):
    game.rate_game = CoroMock()
    game.state = GameState.LIVE
    game.launched_at = time.time()
    await game.on_game_end()
    assert game.state == GameState.ENDED
    game.rate_game.assert_any_call()


async def test_to_dict(game, create_player):
    await game.clear_data()

    game.state = GameState.LOBBY
    players = [
        (create_player(**info), result, team) for info, result, team in [
            (dict(login='Paula_Bean', id=1, global_rating=Rating(1500, 250.7)), 0, 1),
            (dict(login='Some_Guy', id=2, global_rating=Rating(1700, 120.1)), 0, 1),
            (dict(login='Some_Other_Guy', id=3, global_rating=Rating(1200, 72.02)), 0, 2),
            (dict(login='That_Person', id=4, global_rating=Rating(1200, 72.02)), 0, 2),
        ]
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    game.host = players[0][0]
    await game.launch()
    data = game.to_dict()
    expected = {
        "command": "game_info",
        "visibility": VisibilityState.to_string(game.visibility),
        "password_protected": game.password is not None,
        "uid": game.id,
        "title": game.name,
        "state": 'playing',
        "featured_mod": game.game_mode,
        "featured_mod_versions": game.getGamemodVersion(),
        "sim_mods": game.mods,
        "mapname": game.map_folder_name,
        "map_file_path": game.map_file_path,
        "host": game.host.login,
        "num_players": len(game.players),
        "game_type": game.gameType,
        "max_players": game.max_players,
        "launched_at": game.launched_at,
        "teams": {
            team: [player.login for player in game.players
                   if game.get_player_option(player.id, 'Team') == team]
            for team in game.teams
        }
    }
    assert data == expected

async def test_persist_results(game):
    await game.clear_data()

    game.state = GameState.LOBBY
    players = [
        Player(id=1, login='Dostya', global_rating=(1500, 500)),
        Player(id=2, login='Rhiza', global_rating=(1500, 500))
    ]
    add_connected_players(game, players)
    await game.launch()
    assert len(game.players) == 2
    await game.add_result(0, 1, 'VICTORY', 5)
    await game.on_game_end()

    assert game.get_army_result(1) == 5
    assert len(game.players) == 2

    await game.load_results()
    assert game.get_army_result(1) == 5


def test_equality(game):
    assert game == game
    assert game != Game(5, mock.Mock(), mock.Mock())


def test_hashing(game):
    # game.id == 42
    assert {game: 1, Game(42, mock.Mock(), mock.Mock()): 1} == {game: 1}


async def test_report_army_stats_sends_stats_for_defeated_player(game: Game):
    game.id = 43
    game.state = GameState.LOBBY
    players = [
        Player(id=1, login='Dostya', global_rating=(1500, 500)),
        Player(id=2, login='Rhiza', global_rating=(1500, 500))
    ]
    add_connected_players(game, players)

    await game.launch()
    await game.add_result(0, 1, 'defeat', -1)

    with open("tests/data/game_stats_simple_win.json", "r") as stats_file:
        stats = stats_file.read()

    await game.report_army_stats(stats)

    game._game_stats_service.process_game_stats.assert_called_once_with(players[1], game, stats)

async def test_players_exclude_observers(game: Game):
    game.id = 44
    game.state = GameState.LOBBY
    players = [
        Player(id=1, login='Dostya', global_rating=(1500, 500)),
        Player(id=2, login='Rhiza', global_rating=(1500, 500)),
    ]
    add_connected_players(game, players)

    obs = Player(id=3, login='Zoidberg', global_rating=(1500, 500))

    game.game_service.player_service[obs.id] = obs
    gc = mock_game_connection(state=GameConnectionState.CONNECTED_TO_HOST, player=obs)
    game.set_player_option(obs.id, 'Army', -1)
    game.set_player_option(obs.id, 'StartSpot', -1)
    game.set_player_option(obs.id, 'Team', 0)
    game.set_player_option(obs.id, 'Faction', 0)
    game.set_player_option(obs.id, 'Color', 0)
    game.add_game_connection(gc)
    await game.launch()

    assert game.players == frozenset(players)
