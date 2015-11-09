import pytest

import server
from server.game_service import GameService
from server.games.game import VisibilityState
from server.players import PlayerState


@pytest.fixture
def service(players, game_stats_service):
    return GameService(players, game_stats_service)


def test_initialization(service):
    assert len(service.dirty_games) == 0


def test_create_game(players, service):
    players.hosting.state = PlayerState.IDLE
    game = service.create_game(visibility=VisibilityState.PUBLIC,
                               game_mode='faf',
                               host=players.hosting,
                               name='Test',
                               mapname='SCMP_007',
                               password=None)
    assert game is not None
    assert game in service.dirty_games


def test_all_games(players, service):
    game = service.create_game(visibility=VisibilityState.PUBLIC,
                               game_mode='faf',
                               host=players.hosting,
                               name='Test',
                               mapname='SCMP_007',
                               password=None)
    assert game in service.pending_games
