import pytest

from server.db.models import game_stats
from server.exceptions import DisabledError
from server.games import CustomGame, Game, LadderGame, VisibilityState
from server.players import PlayerState


async def test_initialization(game_service):
    assert len(game_service._dirty_games) == 0
    assert game_service.pop_dirty_games() == set()


async def test_initialize_game_counter_empty(game_service, database):
    async with database.acquire() as conn:
        await conn.execute("SET FOREIGN_KEY_CHECKS=0")
        await conn.execute(game_stats.delete())

    await game_service.initialise_game_counter()

    assert game_service.game_id_counter == 0


async def test_graceful_shutdown(game_service):
    await game_service.graceful_shutdown()

    with pytest.raises(DisabledError):
        game_service.create_game(
            game_mode="faf",
        )


async def test_create_game(players, game_service):
    players.hosting.state = PlayerState.IDLE
    game = game_service.create_game(
        visibility=VisibilityState.PUBLIC,
        game_mode="faf",
        host=players.hosting,
        name="Test",
        mapname="SCMP_007",
        password=None
    )
    assert game is not None
    assert game in game_service.pop_dirty_games()
    assert isinstance(game, CustomGame)

    game_service.remove_game(game)
    assert game not in game_service._games


async def test_all_games(players, game_service):
    game = game_service.create_game(
        visibility=VisibilityState.PUBLIC,
        game_mode="faf",
        host=players.hosting,
        name="Test",
        mapname="SCMP_007",
        password=None
    )
    assert game in game_service.pending_games
    assert isinstance(game, CustomGame)


async def test_create_game_ladder1v1(players, game_service):
    game = game_service.create_game(
        game_mode="ladder1v1",
        game_class=LadderGame,
        host=players.hosting,
        name="Test Ladder",
    )
    assert game is not None
    assert game in game_service.pop_dirty_games()
    assert isinstance(game, LadderGame)
    assert game.game_mode == "ladder1v1"


async def test_create_game_other_gamemode(players, game_service):
    game = game_service.create_game(
        visibility=VisibilityState.PUBLIC,
        game_mode="labwars",
        host=players.hosting,
        name="Test",
        mapname="SCMP_007",
        password=None
    )
    assert game is not None
    assert game in game_service.pop_dirty_games()
    assert isinstance(game, Game)
    assert game.game_mode == "labwars"
