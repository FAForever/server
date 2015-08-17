import server
from server.game_service import GameService
from server.games.game import VisibilityState
from server.players import PlayerState

def test_initialization(loop, players, db_pool):
    service = GameService(players)
    assert len(service.dirty_games) == 0


def test_create_game(loop, players, db_pool):
    players.hosting.state = PlayerState.IDLE
    service = GameService(players)
    game = service.create_game(visibility=VisibilityState.PUBLIC,
                               game_mode='faf',
                               host=players.hosting,
                               name='Test',
                               mapname='SCMP_007',
                               password=None)
    assert game is not None
    assert game in service.dirty_games

def test_all_games(loop, players, db_pool):
    service = GameService(players)
    game = service.create_game(visibility=VisibilityState.PUBLIC,
                               game_mode='faf',
                               host=players.hosting,
                               name='Test',
                               mapname='SCMP_007',
                               password=None)
    assert game in service.pending_games
