import server
from server.game_service import GameService


def test_initialization(players, db):
    service = GameService(players, db)
    assert len(service.dirty_games) == 0


def test_create_game(players, db):
    players.hosting.action = ''
    service = GameService(players, db)
    game = service.create_game(visibility='public',
                               game_mode='faf',
                               host=players.hosting,
                               name='Test',
                               mapname='SCMP_007',
                               password=None,
                               version=None)
    assert game is not None
    assert game in service.dirty_games

def test_all_games(players, db):
    service = GameService(players, db)
    game = service.create_game(visibility='public',
                               game_mode='faf',
                               host=players.hosting,
                               name='Test',
                               mapname='SCMP_007',
                               password=None,
                               version=None)
    assert game in service.active_games

def test_all_game_modes(players, db):
    service = GameService(players, db)
    game_modes = service.all_game_modes()

    for info in game_modes:
        assert info['name'] in map(lambda f: f[0], server.games.game_modes)
        assert info['fullname'] in map(lambda f: f[1], server.games.game_modes)
