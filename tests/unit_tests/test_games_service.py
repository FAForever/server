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
    assert game in service.all_games()
