import random
from mock import patch

from tests.unit_tests.ladder_fixtures import *


def test_choose_ladder_map_pool_nonempty(container, ladder_setup):
    container.popular_maps = mock.Mock(return_value=ladder_setup['popular_maps'])
    container.selected_maps = mock.Mock(return_value=ladder_setup['player1_maps'])
    pool = container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])

    assert len(pool) > 0


def test_choose_ladder_map_pool_selects_from_p1_and_popular(container, ladder_setup):
    with patch('random.choice', lambda s: ladder_setup['player1_maps']):
        container.popular_maps = mock.Mock(return_value=ladder_setup['popular_maps'])
        container.selected_maps = mock.Mock(return_value=ladder_setup['player1_maps'])

        expected_map_pool = ladder_setup['player1_maps'] & ladder_setup['player2_maps']
        expected_map_pool |= ladder_setup['player1_maps'] | ladder_setup['popular_maps']

        actual_pool = container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])
        assert expected_map_pool == actual_pool


def test_choose_ladder_map_pool_selects_from_p2_and_popular(container, ladder_setup):
    with patch('random.choice', lambda s: ladder_setup['player2_maps']):
        container.popular_maps = mock.Mock(return_value=ladder_setup['popular_maps'])
        container.selected_maps = mock.Mock(return_value=ladder_setup['player2_maps'])

        expected_map_pool = ladder_setup['player2_maps'] | ladder_setup['popular_maps']

        actual_pool = container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])
        assert expected_map_pool == actual_pool


def test_starts_game_with_map_from_popular(container, ladder_setup):
    with patch('random.choice', lambda s: ladder_setup['popular_maps']):
        container.popular_maps = mock.Mock(return_value=ladder_setup['popular_maps'])

        expected_map_pool = ladder_setup['popular_maps']
        expected_map_pool |= ladder_setup['player1_maps'] & ladder_setup['player2_maps']

        actual_pool = container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])
        assert expected_map_pool == actual_pool


def test_choose_ladder_map_pool_previous_games(container: Ladder1V1GamesContainer, ladder_setup, lobbythread):
    container.get_recent_maps = mock.Mock(return_value=ladder_setup['recently_played'])
    container.selected_maps = mock.Mock(return_value=ladder_setup['player1_maps'])
    pool = container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])

    recent = container.get_recent_maps([ladder_setup['player1'], ladder_setup['player2']])
    assert pool.isdisjoint(recent)


def test_start_game_uses_map_from_mappool(container: Ladder1V1GamesContainer, ladder_setup, lobbythread):
    map_pool = ladder_setup['popular_maps']
    container.choose_ladder_map_pool = mock.Mock(return_value=map_pool)
    lobbythread.sendJSON = mock.Mock()
    container.getMapName = lambda i: i

    container.startGame(ladder_setup['player1'], ladder_setup['player2'])
    args, kwargs = lobbythread.sendJSON.call_args
    assert int(args[0]['mapname']) in map_pool


def test_keeps_track_of_started_games(container, ladder_setup):
    map_pool = ladder_setup['popular_maps']
    container.choose_ladder_map_pool = mock.Mock(return_value=map_pool)

    container.startGame(ladder_setup['player1'], ladder_setup['player2'])
    assert len(container.games) == 1
