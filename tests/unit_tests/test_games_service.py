import server
from server.game_service import GameService
from server.players import PlayerState

def test_initialization(loop, players, db_pool):
    service = GameService(players)
    assert len(service.dirty_games) == 0


def test_create_game(loop, players, db_pool):
    players.hosting.state = PlayerState.IDLE
    service = GameService(players)
    game = service.create_game(visibility='public',
                               game_mode='faf',
                               host=players.hosting,
                               name='Test',
                               mapname='SCMP_007',
                               password=None)
    assert game is not None
    assert game in service.dirty_games

def test_all_games(loop, players, db, db_pool):
    service = GameService(players, db)
    game = service.create_game(visibility='public',
                               game_mode='faf',
                               host=players.hosting,
                               name='Test',
                               mapname='SCMP_007',
                               password=None)
    assert game in service.active_games

def test_all_game_modes(loop, players, db, db_pool):
    service = GameService(players, db)
    game_modes = service.all_game_modes()

    for info in game_modes:
        assert info['name'] in map(lambda f: f[0], server.games.game_modes)
        assert info['fullname'] in map(lambda f: f[1], server.games.game_modes)
