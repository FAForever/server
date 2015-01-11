from gameModes import ladderGamesContainer, ladder1v1GamesContainerClass

import pytest
import random
from PySide import QtSql
from flexmock import flexmock

from ladder_fixtures import *


class DictMatcher(object):
    def __init__(self, obj, exp):
        self.obj = obj
        self.exp = exp

    def __eq__(self, other):
        return self.exp(self.obj, other)


def assert_mapname_in(exp, obj):
    assert int(obj['mapname']) in exp
    return True


def test_starts_game_with_map_from_player1_and_popular(monkeypatch, container, ladder_setup, lobbythread):
    monkeypatch.setattr(random, 'randint', lambda a, b: 1)

    flexmock(container)
    container.should_receive('getSelectedLadderMaps').replace_with(lambda x: ladder_setup['player1_maps'])
    container.should_receive('getMapName').replace_with(lambda i: i)
    container.should_receive('getPopularLadderMaps').replace_with(lambda x: ladder_setup['popular_maps'])

    (lobbythread.should_receive('sendJSON')
                .with_args(DictMatcher(ladder_setup['popular_maps'] + ladder_setup['player1_maps'],
                                       assert_mapname_in)))

    container.startGame(ladder_setup['player1'], ladder_setup['player2'])


def test_starts_game_with_map_from_player2_and_popular(monkeypatch, container, ladder_setup, lobbythread):
    monkeypatch.setattr(random, 'randint', lambda a, b: 2)

    flexmock(container)
    container.should_receive('getSelectedLadderMaps').replace_with(lambda x: ladder_setup['player2_maps'])
    container.should_receive('getMapName').replace_with(lambda i: i)
    container.should_receive('getPopularLadderMaps').replace_with(lambda x: ladder_setup['popular_maps'])

    (lobbythread.should_receive('sendJSON')
     .with_args(DictMatcher(ladder_setup['popular_maps'] + ladder_setup['player2_maps'],
                            assert_mapname_in)))

    container.startGame(ladder_setup['player1'], ladder_setup['player2'])


def test_starts_game_with_map_with_popular(monkeypatch, container, ladder_setup, lobbythread):
    monkeypatch.setattr(random, 'randint', lambda a, b: 0)

    flexmock(container)
    container.should_receive('getMapName').replace_with(lambda i: i)
    container.should_receive('getPopularLadderMaps').replace_with(lambda x: ladder_setup['popular_maps'])

    (lobbythread.should_receive('sendJSON')
     .with_args(DictMatcher(ladder_setup['popular_maps']
                            + list(set(ladder_setup['player1_maps']).intersection(set(ladder_setup['player2_maps']))),
                            assert_mapname_in)))

    container.startGame(ladder_setup['player1'], ladder_setup['player2'])
