import random

from tests.unit_tests.ladder_fixtures import *


def test_choose_ladder_map_pool_selects_from_p1_and_popular(monkeypatch, container, ladder_setup):
    monkeypatch.setattr(random, 'randint', lambda a, b: 1)
    container.getPopularLadderMaps = mock.Mock(return_value=ladder_setup['popular_maps'])
    container.getSelectedLadderMaps = mock.Mock(return_value=ladder_setup['player1_maps'])

    expected_map_pool = ladder_setup['player1_maps'] + ladder_setup['popular_maps']

    assert (set(container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2']))
            == set(expected_map_pool))


def test_choose_ladder_map_pool_selects_from_p2_and_popular(monkeypatch, container, ladder_setup):
    monkeypatch.setattr(random, 'randint', lambda a, b: 2)
    container.getPopularLadderMaps = mock.Mock(return_value=ladder_setup['popular_maps'])
    container.getSelectedLadderMaps = mock.Mock(return_value=ladder_setup['player2_maps'])

    expected_map_pool = ladder_setup['player2_maps'] + ladder_setup['popular_maps']

    assert (set(container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2']))
            == set(expected_map_pool))


def test_starts_game_with_map_from_popular(monkeypatch, container, ladder_setup):
    monkeypatch.setattr(random, 'randint', lambda a, b: 0)
    container.getPopularLadderMaps = mock.Mock(return_value=ladder_setup['popular_maps'])

    expected_map_pool = (ladder_setup['popular_maps']
                         + list(set(ladder_setup['player1_maps'])
                                .intersection(set(ladder_setup['player2_maps']))))

    assert (set(container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2']))
            == set(expected_map_pool))


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
