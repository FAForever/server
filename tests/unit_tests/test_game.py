import logging
import time
from typing import Any, List, Tuple
from unittest import mock

import pytest
from mock import patch
from server.gameconnection import GameConnection, GameConnectionState
from server.games import CoopGame, CustomGame
from server.games.game import (Game, GameError, GameOutcome, GameState,
                               ValidityState, Victory, VisibilityState)
from server.players import Player
from tests import CoroMock
from tests.unit_tests.conftest import (add_connected_player,
                                       add_connected_players, add_players,
                                       make_mock_game_connection)
from trueskill import Rating


@pytest.yield_fixture
def game(loop, game_service, game_stats_service):
    game = Game(42, game_service, game_stats_service)
    yield game
    loop.run_until_complete(game.clear_data())


@pytest.yield_fixture
def coop_game(loop, game_service, game_stats_service):
    game = CoopGame(42, game_service, game_stats_service)
    yield game
    loop.run_until_complete(game.clear_data())


@pytest.yield_fixture
def custom_game(loop, game_service, game_stats_service):
    game = CustomGame(42, game_service, game_stats_service)
    yield game
    loop.run_until_complete(game.clear_data())


def test_initialization(game: Game):
    assert game.state == GameState.INITIALIZING
    assert game.enforce_rating is False


def test_instance_logging(game_stats_service):
    logger = logging.getLogger('{}.5'.format(Game.__qualname__))
    logger.debug = mock.Mock()
    mock_parent = mock.Mock()
    game = Game(5, mock_parent, game_stats_service)
    logger.debug.assert_called_with("%s created", game)


async def test_validate_game_settings(game: Game):
    settings = [
        ('Victory', Victory.SANDBOX, ValidityState.WRONG_VICTORY_CONDITION),
        ('FogOfWar', 'none', ValidityState.NO_FOG_OF_WAR),
        ('CheatsEnabled', 'true', ValidityState.CHEATS_ENABLED),
        ('PrebuiltUnits', 'On', ValidityState.PREBUILT_ENABLED),
        ('NoRushOption', 20, ValidityState.NORUSH_ENABLED),
        ('RestrictedCategories', 1, ValidityState.BAD_UNIT_RESTRICTIONS),
        ('TeamLock', 'unlocked', ValidityState.UNLOCKED_TEAMS)
    ]

    game.state = GameState.LOBBY
    add_players(game, 2)

    await check_game_settings(game, settings)

    game.validity = ValidityState.VALID
    await game.validate_game_settings()
    assert game.validity is ValidityState.VALID


async def test_validate_game_settings_coop(coop_game: Game):
    settings = [
        ('Victory', Victory.DEMORALIZATION, ValidityState.WRONG_VICTORY_CONDITION),
        ('TeamSpawn', 'open', ValidityState.SPAWN_NOT_FIXED),
        ('RevealedCivilians', 'Yes', ValidityState.CIVILIANS_REVEALED),
        ('Difficulty', 1, ValidityState.WRONG_DIFFICULTY),
        ('Expansion', 0, ValidityState.EXPANSION_DISABLED),
    ]

    await check_game_settings(coop_game, settings)

    coop_game.validity = ValidityState.VALID
    await coop_game.validate_game_settings()
    assert coop_game.validity is ValidityState.VALID


async def check_game_settings(game: Game, settings: List[Tuple[str, Any, ValidityState]]):
    for key, value, expected in settings:
        old = game.gameOptions.get(key)
        game.gameOptions[key] = value
        await game.validate_game_settings()
        assert game.validity is expected
        game.gameOptions[key] = old


async def test_ffa_not_rated(game):
    game.state = GameState.LOBBY
    add_players(game, 5, team=1)

    await game.launch()
    await game.add_result(0, 1, 'VICTORY', 5)

    game.launched_at = time.time() - 60*20 # seconds

    await game.on_game_end()
    assert game.validity == ValidityState.FFA_NOT_RANKED


async def test_multi_team_not_rated(game):
    game.state = GameState.LOBBY
    add_players(game, 2, team=1)
    add_players(game, 2, team=2)
    add_players(game, 2, team=3)
    await game.launch()
    await game.add_result(0, 1, 'VICTORY', 5)
    game.launched_at = time.time() - 60*20 # seconds
    await game.on_game_end()
    assert game.validity == ValidityState.MULTI_TEAM


async def test_has_ai_players_not_rated(game):
    game.state = GameState.LOBBY
    add_players(game, 2, team=1)
    add_players(game, 2, team=2)
    game.AIs = {'IA Tech': {'Faction': 5, 'Color': 1, 'Team': 2, 'StartSpot': 2}, 'Oum-Ashavoh (IA Tech)': {'Army': 3}}
    await game.launch()
    await game.add_result(0, 1, 'VICTORY', 5)
    game.launched_at = time.time() - 60*20 # seconds
    await game.on_game_end()
    assert game.validity == ValidityState.HAS_AI_PLAYERS


async def test_uneven_teams_not_rated(game):
    game.state = GameState.LOBBY
    add_players(game, 2, team=2)
    add_players(game, 3, team=3)

    await game.launch()
    await game.add_result(0, 1, 'VICTORY', 5)

    game.launched_at = time.time() - 60*20 # seconds

    await game.on_game_end()
    assert game.validity == ValidityState.UNEVEN_TEAMS_NOT_RANKED


async def test_single_team_not_rated(game):
    n_players = 4
    game.state = GameState.LOBBY
    add_players(game, n_players, team=2)

    await game.launch()
    game.launched_at = time.time()-60*20
    for i in range(n_players):
        await game.add_result(0, i+1, 'victory', 5)
    await game.on_game_end()

    assert game.validity is ValidityState.UNEVEN_TEAMS_NOT_RANKED


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


def test_invalid_get_player_option_key(game: Game, players):
    assert game.get_player_option(players.hosting.id, -1) is None


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


async def test_game_sim_ends_when_no_more_connections(game: Game, players):
    await game.clear_data()
    game.state = GameState.LOBBY
    host_conn = add_connected_player(game, players.hosting)
    join_conn = add_connected_player(game, players.joining)
    game.host = players.hosting

    await game.launch()

    await game.remove_game_connection(host_conn)
    await game.remove_game_connection(join_conn)
    assert game.ended


async def test_game_sim_ends_when_connections_ended_sim(game: Game, players):
    await game.clear_data()
    game.state = GameState.LOBBY
    host_conn = add_connected_player(game, players.hosting)
    join_conn = add_connected_player(game, players.joining)
    game.host = players.hosting

    await game.launch()

    host_conn.finished_sim = True
    join_conn.finished_sim = True
    await game.check_sim_end()
    assert game.ended


async def test_game_marked_dirty_when_timed_out(game: Game):
    game.state = GameState.INITIALIZING
    game.sleep = CoroMock()
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
    game.set_ai_option('rush', 'StartSpot', 3)

    game.clear_slot(0)
    game.clear_slot(3)

    assert game.get_player_option(1, 'StartSpot') == -1
    assert game.get_player_option(1, 'Team') == -1
    assert game.get_player_option(1, 'Army') == -1
    assert game.get_player_option(2, 'StartSpot') == 1
    assert 'rush' not in game.AIs


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


async def test_invalid_army_not_add_result(game: Game, players):
    await game.add_result(players.hosting, 99, "win", 10)

    assert 99 not in game._results


async def test_game_ends_in_mutually_agreed_draw(game: Game):
    game.state = GameState.LOBBY
    players = add_players(game, 2)

    await game.launch()
    game.launched_at = time.time()-60*60

    await game.add_result(players[0], 0, 'mutual_draw', 0)
    await game.add_result(players[1], 1, 'mutual_draw', 0)
    await game.on_game_end()

    assert game.validity is ValidityState.MUTUAL_DRAW


async def test_game_not_ends_in_unilatery_agreed_draw(game: Game, players):
    game.state = GameState.LOBBY
    add_players(game, 2)

    await game.launch()
    game.launched_at = time.time()-60*60

    await game.add_result(players.hosting, 0, 'mutual_draw', 0)
    await game.add_result(players.joining, 1, 'victory', 10)
    await game.on_game_end()

    assert game.validity is not ValidityState.MUTUAL_DRAW


async def test_game_is_invalid_due_to_desyncs(game: Game, players):
    await game.clear_data()
    game.state = GameState.LOBBY
    add_connected_players(game, [players.hosting, players.joining])
    game.host = players.hosting

    await game.launch()
    game.desyncs = 30
    await game.on_game_end()

    assert game.validity is ValidityState.TOO_MANY_DESYNCS


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


async def test_game_get_army_result_takes_most_reported_result(game):

    game.state = GameState.LOBBY
    players = add_players(game, 1)
    await game.add_result(0, 0, 'defeat', 0)
    await game.add_result(0, 0, 'defeat', 0)
    await game.add_result(0, 0, 'victory', 0)

    assert game.get_army_result(players[0]) == 'defeat'

    await game.add_result(0, 0, 'victory', 0)
    await game.add_result(0, 0, 'victory', 0)

    assert game.get_army_result(players[0]) == 'victory'


async def test_on_game_end_does_not_call_rate_game_for_single_player(game):
    game.rate_game = CoroMock()
    game.state = GameState.LIVE
    game.launched_at = time.time()

    await game.on_game_end()
    assert game.state == GameState.ENDED
    game.rate_game.assert_not_called()


async def test_on_game_end_calls_rate_game_with_two_players(game):
    await game.clear_data()
    game.rate_game = CoroMock()
    game.state = GameState.LOBBY
    add_players(game, 2)

    await game.launch()

    assert len(game.players) == 2
    await game.add_result(0, 1, 'victory', 10)
    await game.add_result(1, 2, 'defeat', -10)

    await game.on_game_end()
    assert game.state == GameState.ENDED
    game.rate_game.assert_any_call()

    assert game.validity is ValidityState.VALID


async def test_name_sanitization(game):
    await game.clear_data()
    game.state = GameState.LOBBY
    game.name = game.sanitize_name("卓☻иAâé~<1000")
    try:
        game.name.encode('utf-16-be').decode('ascii')
    except UnicodeDecodeError:
        pass

    assert(game.name == "_Aâé~<1000")


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
        "title": game.sanitize_name(game.name),
        "state": 'playing',
        "featured_mod": game.game_mode,
        "featured_mod_versions": game.getGamemodVersion(),
        "sim_mods": game.mods,
        "mapname": game.map_folder_name,
        "map_file_path": game.map_file_path,
        "host": game.host.login,
        "num_players": len(game.players),
        "max_players": game.max_players,
        "launched_at": game.launched_at,
        "teams": {
            team: [player.login for player in game.players
                   if game.get_player_option(player.id, 'Team') == team]
            for team in game.teams
        }
    }
    assert data == expected


async def test_persist_results_not_called_with_one_player(game):
    await game.clear_data()
    game.persist_results = CoroMock()

    game.state = GameState.LOBBY
    players = [
        Player(id=1, login='Dostya', global_rating=(1500, 500))
    ]
    add_connected_players(game, players)
    await game.launch()
    assert len(game.players) == 1
    await game.add_result(0, 1, 'VICTORY', 5)
    await game.on_game_end()

    game.persist_results.assert_not_called()


async def test_persist_results_not_called_with_no_results(game):
    game.state = GameState.LOBBY
    add_players(game, 2, team=2)
    add_players(game, 2, team=3)
    game.persist_results = CoroMock()
    game.launched_at = time.time() - 60*20

    await game.launch()
    await game.on_game_end()

    assert len(game.players) == 4
    assert len(game._results) == 0
    assert game.validity is ValidityState.UNKNOWN_RESULT
    game.persist_results.assert_not_called()


async def test_persist_results_called_with_two_players(game):
    await game.clear_data()
    game.state = GameState.LOBBY
    add_players(game, 2)
    await game.launch()
    assert len(game.players) == 2
    await game.add_result(0, 1, 'victory', 5)
    await game.on_game_end()

    assert game.get_army_score(1) == 5
    assert len(game.players) == 2

    await game.load_results()
    assert game.get_army_score(1) == 5


async def test_persist_results_called_for_unranked(game):
    await game.clear_data()
    game.state = GameState.LOBBY
    add_players(game, 2)
    await game.launch()
    game.validity = ValidityState.BAD_UNIT_RESTRICTIONS
    assert len(game.players) == 2
    await game.add_result(0, 1, 'victory', 5)
    await game.on_game_end()

    assert game.get_army_score(1) == 5
    assert len(game.players) == 2

    await game.load_results()
    assert game.get_army_score(1) == 5


async def test_get_army_score_conflicting_results_clear_winner(game):
    game.state = GameState.LOBBY
    add_players(game, 3, team=2)
    add_players(game, 3, team=3)
    await game.launch()

    await game.add_result(0, 0, 'victory', 1000)
    await game.add_result(1, 0, 'victory', 1234)
    await game.add_result(2, 0, 'victory', 1234)
    await game.add_result(3, 1, 'defeat', 100)
    await game.add_result(4, 1, 'defeat', 123)
    await game.add_result(5, 1, 'defeat', 100)

    # Choose the most frequently reported score
    assert game.get_army_score(0) == 1234
    assert game.get_army_score(1) == 100


async def test_get_army_score_conflicting_results_tied(game):
    game.state = GameState.LOBBY
    add_players(game, 2, team=2)
    add_players(game, 2, team=3)
    await game.add_result(0, 0, 'victory', 1000)
    await game.add_result(1, 0, 'victory', 1234)
    await game.add_result(2, 1, 'defeat', 100)
    await game.add_result(3, 1, 'defeat', 123)

    # Choose the highest score
    assert game.get_army_score(0) == 1234
    assert game.get_army_score(1) == 123


def test_equality(game):
    assert game == game
    assert game != Game(5, mock.Mock(), mock.Mock())


def test_hashing(game):
    assert {game: 1, Game(game.id, mock.Mock(), mock.Mock()): 1} == {game: 1}


async def test_report_army_stats_sends_stats_for_defeated_player(game: Game):
    game.state = GameState.LOBBY
    players = add_players(game, 2)

    await game.launch()
    await game.add_result(0, 1, 'defeat', -1)

    with open("tests/data/game_stats_simple_win.json", "r") as stats_file:
        stats = stats_file.read()

    await game.report_army_stats(stats)

    game._game_stats_service.process_game_stats.assert_called_once_with(players[1], game, stats)


async def test_partial_stats_not_affecting_rating_persistence(custom_game, event_service, achievement_service):
    from server.stats.game_stats_service import GameStatsService
    game = custom_game
    game._game_stats_service = GameStatsService(event_service, achievement_service)
    game.state = GameState.LOBBY
    players = add_players(game, 2)
    game.set_player_option(players[0].id, 'Team', 2)
    game.set_player_option(players[1].id, 'Team', 3)
    old_mean = players[0].global_rating[0]

    await game.launch()
    game.launched_at = time.time()-60*60
    await game.add_result(0, 0, 'victory', 10)
    await game.add_result(0, 1, 'defeat', -10)
    await game.report_army_stats({'stats': {'Player 1': {}}})
    await game.on_game_end()

    assert game.validity is ValidityState.VALID
    assert players[0].global_rating[0] > old_mean


async def test_players_exclude_observers(game: Game):
    game.state = GameState.LOBBY
    players = add_players(game, 2)

    obs = Player(id=3, login='Zoidberg', global_rating=(1500, 500))

    game.game_service.player_service[obs.id] = obs
    gc = make_mock_game_connection(state=GameConnectionState.CONNECTED_TO_HOST, player=obs)
    game.set_player_option(obs.id, 'Army', -1)
    game.set_player_option(obs.id, 'StartSpot', -1)
    game.set_player_option(obs.id, 'Team', 0)
    game.set_player_option(obs.id, 'Faction', 0)
    game.set_player_option(obs.id, 'Color', 0)
    game.add_game_connection(gc)
    await game.launch()

    assert game.players == frozenset(players)


async def test_game_outcomes(game: Game, players):
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

    host_outcome = game.outcome(players.hosting)
    guest_outcome = game.outcome(players.joining)
    assert host_outcome is GameOutcome.VICTORY
    assert guest_outcome is GameOutcome.DEFEAT


async def test_game_outcomes_no_results(game: Game, players):
    await game.clear_data()

    game.state = GameState.LOBBY
    players.hosting.ladder_rating = Rating(1500, 250)
    players.joining.ladder_rating = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 1)

    host_outcome = game.outcome(players.hosting)
    guest_outcome = game.outcome(players.joining)
    assert host_outcome is None
    assert guest_outcome is None


async def test_game_outcomes_conflicting(game: Game, players):
    await game.clear_data()

    game.state = GameState.LOBBY
    players.hosting.ladder_rating = Rating(1500, 250)
    players.joining.ladder_rating = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    await game.add_result(players.hosting, 0, 'victory', 1)
    await game.add_result(players.joining, 1, 'victory', 0)
    await game.add_result(players.hosting, 0, 'defeat', 1)
    await game.add_result(players.joining, 1, 'defeat', 0)
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 1)

    host_outcome = game.outcome(players.hosting)
    guest_outcome = game.outcome(players.joining)
    assert host_outcome is None
    assert guest_outcome is None


def test_victory_conditions():
    conds = [("demoralization", Victory.DEMORALIZATION),
             ("domination", Victory.DOMINATION),
             ("eradication", Victory.ERADICATION),
             ("sandbox", Victory.SANDBOX)]

    for string_value, enum_value in conds:
        assert Victory.from_gpgnet_string(string_value) == enum_value


def test_visibility_states():
    states = [("public", VisibilityState.PUBLIC),
              ("friends", VisibilityState.FRIENDS)]

    for string_value, enum_value in states:
        assert (VisibilityState.from_string(string_value) == enum_value and
                VisibilityState.to_string(enum_value) == string_value)


def test_is_even(game: Game):
    game.state = GameState.LOBBY
    add_players(game, 4, team=2)
    add_players(game, 4, team=3)

    assert game.is_even


def test_is_even_no_players(game: Game):
    game.state = GameState.LOBBY

    assert game.is_even


def test_is_even_single_player(game: Game):
    game.state = GameState.LOBBY
    add_players(game, 2, team=2)

    assert not game.is_even


def test_is_even_ffa(game: Game):
    game.state = GameState.LOBBY
    # Team 1 is the special "-" team
    add_players(game, 5, team=1)

    assert game.is_even
