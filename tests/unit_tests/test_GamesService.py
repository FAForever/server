from src.games import gamesContainerClass
from src.games_service import GamesService


def test_initialization(players, db):
    service = GamesService(players, db)
    assert service.dirty_games == []


def test_create_game(players, db):
    players.hosting.action = ''
    service = GamesService(players, db)
    service.addContainer('faf', gamesContainerClass("faf", "Forged Alliance Forever", db, service))
    game = service.create_game("public", 'faf', players.hosting, 'Some_game_name', 6112, 'scmp_007')
    assert game is not None
    assert game.id in service.dirty_games
