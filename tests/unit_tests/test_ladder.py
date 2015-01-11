import random

from tests.unit_tests.ladder_fixtures import *


class DictMatcher(object):
    def __init__(self, obj, exp):
        self.obj = obj
        self.exp = exp

    def __eq__(self, other):
        return self.exp(self.obj, other)


def assert_mapname_in(exp, obj):
    assert int(obj['mapname']) in exp
    return True


def test_choose_ladder_map_pool_selects_from_p1_and_popular(monkeypatch, container, ladder_setup):
    monkeypatch.setattr(random, 'randint', lambda a, b: 1)

    flexmock(container)
    container.should_receive('getSelectedLadderMaps').replace_with(lambda x: ladder_setup['player1_maps'])
    container.should_receive('getPopularLadderMaps').replace_with(lambda x: ladder_setup['popular_maps'])

    expected_map_pool = ladder_setup['player1_maps'] + ladder_setup['popular_maps']

    assert (set(container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2']))
            == set(expected_map_pool))


def test_choose_ladder_map_pool_selects_from_p2_and_popular(monkeypatch, container, ladder_setup):
    monkeypatch.setattr(random, 'randint', lambda a, b: 2)

    flexmock(container)
    container.should_receive('getSelectedLadderMaps').replace_with(lambda x: ladder_setup['player2_maps'])
    container.should_receive('getPopularLadderMaps').replace_with(lambda x: ladder_setup['popular_maps'])

    expected_map_pool = ladder_setup['player2_maps'] + ladder_setup['popular_maps']

    assert (set(container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2']))
            == set(expected_map_pool))


def test_starts_game_with_map_from_popular(monkeypatch, container, ladder_setup):
    monkeypatch.setattr(random, 'randint', lambda a, b: 0)

    flexmock(container)
    container.should_receive('getPopularLadderMaps').replace_with(lambda x: ladder_setup['popular_maps'])

    expected_map_pool = (ladder_setup['popular_maps']
                         + list(set(ladder_setup['player1_maps'])
                                .intersection(set(ladder_setup['player2_maps']))))

    assert (set(container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2']))
            == set(expected_map_pool))


def test_start_game_uses_map_from_mappool(container, ladder_setup, lobbythread):
    flexmock(container)

    map_pool = ladder_setup['popular_maps']
    container.should_receive('choose_ladder_map_pool').and_return(map_pool)
    container.should_receive('getMapName').replace_with(lambda i: i)
    lobbythread.should_receive('sendJSON').with_args((DictMatcher(map_pool, assert_mapname_in)))

    container.startGame(ladder_setup['player1'], ladder_setup['player2'])
