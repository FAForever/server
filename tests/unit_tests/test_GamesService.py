from server.games import GamesContainer
from server.game_service import GameService


def test_initialization(players, db):
    service = GameService(players, db)
    assert len(service.dirty_games) == 0


def test_create_game(players, db):
    players.hosting.action = ''
    service = GameService(players, db)
    service.addContainer('faf', GamesContainer("faf", "Forged Alliance Forever", db, service))
    game = service.create_game("public", 'faf', players.hosting, 'Some_game_name', 6112, 'scmp_007')
    assert game is not None
    assert game in service.dirty_games
