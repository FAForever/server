import logging
from unittest import mock
import asyncio

import pytest

from trueskill import Rating
from server.games.game import Game, GameState, GameError, VisibilityState
from server.gameconnection import GameConnection, GameConnectionState


@pytest.fixture()
def game(game_service):
    return Game(42, game_service)


def test_initialization(game: Game):
    assert game.state == GameState.INITIALIZING


def test_instance_logging():
    logger = logging.getLogger('{}.5'.format(Game.__qualname__))
    logger.info = mock.Mock()
    mock_parent = mock.Mock()
    game = Game(5, mock_parent)
    logger.info.assert_called_with("{} created".format(game))


@pytest.fixture
def game_connection(state=GameConnectionState.INITIALIZING, player=None):
    gc = mock.create_autospec(spec=GameConnection)
    gc.state = state
    gc.player = player
    return gc


def add_connected_player(game: Game, player):
    game.add_game_connection(game_connection(state=GameConnectionState.CONNECTED_TO_HOST, player=player))


def add_connected_players(game: Game, players):
    """
    Utility to add players with army and StartSpot indexed by a list
    """
    for army, player in enumerate(players):
        add_connected_player(game, player)
        game.set_player_option(player.id, 'Army', army)
        game.set_player_option(player.id, 'StartSpot', army)


def test_set_player_option(game, players, game_connection):
    game.state = GameState.LOBBY
    game_connection.player = players.hosting
    game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(game_connection)
    assert game.players == {players.hosting}
    game.set_player_option(players.hosting.id, 'Team', 1)
    assert game.get_player_option(players.hosting.id, 'Team') == 1
    assert game.teams == {1}
    game.set_player_option(players.hosting.id, 'StartSpot', 1)
    game.get_player_option(players.hosting.id, 'StartSpot') == 1


def test_add_game_connection(game: Game, players, game_connection):
    game.state = GameState.LOBBY
    game_connection.player = players.hosting
    game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(game_connection)
    assert players.hosting in game.players


def test_add_game_connection_throws_if_not_connected_to_host(game: Game, players, game_connection):
    game.state = GameState.LOBBY
    game_connection.player = players.hosting
    game_connection.state = GameConnectionState.INITIALIZED
    with pytest.raises(GameError):
        game.add_game_connection(game_connection)

    assert players.hosting not in game.players


def test_add_game_connection_throws_if_not_lobby_state(game: Game, players, game_connection):
    game.state = GameState.INITIALIZING
    game_connection.player = players.hosting
    game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    with pytest.raises(GameError):
        game.add_game_connection(game_connection)

    assert players.hosting not in game.players


def test_remove_game_connection(game: Game, players, game_connection):
    game.state = GameState.LOBBY
    game_connection.player = players.hosting
    game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(game_connection)
    game.remove_game_connection(game_connection)
    assert players.hosting not in game.players


def test_game_end_when_no_more_connections(game: Game, game_connection):
    game.state = GameState.LOBBY
    game.on_game_end = mock.Mock()
    game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(game_connection)
    game.remove_game_connection(game_connection)
    game.on_game_end.assert_any_call()


def test_game_launch_freezes_players(game: Game, players):
    conn1 = game_connection()
    conn1.state = GameConnectionState.CONNECTED_TO_HOST
    conn1.player = players.hosting
    conn2 = game_connection()
    conn2.player = players.joining
    conn2.state = GameConnectionState.CONNECTED_TO_HOST
    game.state = GameState.LOBBY
    game.add_game_connection(conn1)
    game.add_game_connection(conn2)
    game.launch()
    assert game.state == GameState.LIVE
    assert game.players == {players.hosting, players.joining}
    game.remove_game_connection(conn1)
    assert game.players == {players.hosting, players.joining}


@asyncio.coroutine
def test_update_ratings(game: Game, players, db_pool, player_service, game_service):
    player_service.players[players.hosting.id] = players.hosting
    game.state = GameState.LOBBY
    add_connected_player(game, players.hosting)
    yield from game.update_ratings()
    assert players.hosting.global_rating == (2000, 125)


def test_game_teams_represents_active_teams(game: Game, players):
    game.state = GameState.LOBBY
    add_connected_players(game, [players.hosting, players.joining])
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 2)
    assert game.teams == {1, 2}


def test_compute_rating_computes_global_ratings(game: Game, players):
    game.state = GameState.LOBBY
    players.hosting.global_rating = Rating(1500, 250)
    players.joining.global_rating = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    game.launch()
    game.add_result(players.hosting, 0, 'victory', 1)
    game.add_result(players.joining, 1, 'defeat', 0)
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 2)
    groups = game.compute_rating()
    assert players.hosting in groups[0]
    assert players.joining in groups[1]


def test_compute_rating_computes_ladder_ratings(game: Game, players):
    game.state = GameState.LOBBY
    players.hosting.ladder_rating = Rating(1500, 250)
    players.joining.ladder_rating = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    game.launch()
    game.add_result(players.hosting, 0, 'victory', 1)
    game.add_result(players.joining, 1, 'defeat', 0)
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 2)
    groups = game.compute_rating(rating='ladder')
    assert players.hosting in groups[0]
    assert players.joining in groups[1]


def test_compute_rating_balanced_teamgame(game: Game, create_player):
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
    game.launch()
    for player, result, _ in players:
        game.add_result(player, player.id - 1, 'score', result)
    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert player in game.players
            assert new_rating != player.global_rating


def test_on_game_end_calls_rate_game(game):
    game.rate_game = mock.Mock()
    game.state = GameState.LIVE
    game.on_game_end()
    assert game.state == GameState.ENDED
    game.rate_game.assert_any_call()


@asyncio.coroutine
def test_to_dict(game, create_player):
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
    game.launch()
    data = game.to_dict()
    expected = {
        "command": "game_info",
        "visibility": VisibilityState.to_string(game.visibility),
        "password_protected": game.password is not None,
        "uid": game.id,
        "title": game.name,
        "state": 'closed',
        "featured_mod": game.game_mode,
        "featured_mod_versions": game.getGamemodVersion(),
        "sim_mods": game.mods,
        "map_file_path": game.map_file_path.lower(),
        "host": game.host.login,
        "num_players": len(game.players),
        "game_type": game.gameType,
        "options": game.options,
        "max_players": game.max_players,
        "teams": {
            team: [player.login for player in game.players
                   if game.get_player_option(player.id, 'Team') == team]
            for team in game.teams
        }
    }
    assert data == expected

# Eeeeeeeewwwww
def test_equality(game):
    assert game == game
    assert game != Game(5, mock.Mock())
    assert game != True


def test_hashing(game):
    # game.id == 42
    assert {game: 1, Game(42, mock.Mock()): 1} == {game: 1}
