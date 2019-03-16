import pytest
from server.game_service import GameService
from server.games import CustomGame, GameMode, VisibilityState
from server.players import PlayerState


@pytest.fixture
def game_service(players, game_stats_service):
    return GameService(players, game_stats_service)


def test_initialization(game_service):
    assert len(game_service.dirty_games) == 0


def test_create_game(players, game_service):
    players.hosting.state = PlayerState.IDLE
    game = game_service.create_game(
        visibility=VisibilityState.PUBLIC,
        game_mode=GameMode.FAF,
        host=players.hosting,
        name='Test',
        mapname='SCMP_007',
        password=None
    )
    assert game is not None
    assert game in game_service.dirty_games
    assert isinstance(game, CustomGame)


def test_all_games(players, game_service):
    game = game_service.create_game(
        visibility=VisibilityState.PUBLIC,
        game_mode=GameMode.FAF,
        host=players.hosting,
        name='Test',
        mapname='SCMP_007',
        password=None
    )
    assert game in game_service.pending_games
    assert isinstance(game, CustomGame)
