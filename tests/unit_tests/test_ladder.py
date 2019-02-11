from unittest import mock

import pytest
from server import GameService, LadderService
from server.db.models import game_player_stats, game_stats
from server.players import Player
from sqlalchemy import func, text
from tests import CoroMock


@pytest.fixture
def ladder_service(game_service: GameService, db_engine):
    return LadderService(game_service)


async def test_start_game(ladder_service: LadderService, game_service: GameService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p2 = mock.create_autospec(Player('Rhiza', id=2))

    p1.id = 1
    p2.id = 2
    game_service.ladder_maps = [(1, 'scmp_007', 'maps/scmp_007.zip')]

    with mock.patch('asyncio.sleep', CoroMock()):
        await ladder_service.start_game(p1, p2)

    assert p1.lobby_connection.launch_game.called
    assert p2.lobby_connection.launch_game.called


def test_inform_player(ladder_service: LadderService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p1.ladder_rating = (1500, 500)

    ladder_service.inform_player(p1)

    assert p1.lobby_connection.sendJSON.called


async def test_choose_map(ladder_service: LadderService):
    ladder_service.get_ladder_history = CoroMock(
        return_value=[1, 2, 3]
    )

    ladder_service.game_service.ladder_maps = [
        (1, "some_map", "maps/some_map.v001.zip"),
        (2, "some_map", "maps/some_map.v001.zip"),
        (3, "some_map", "maps/some_map.v001.zip"),
        (4, "CHOOSE_ME", "maps/choose_me.v001.zip"),
    ]

    chosen_map = await ladder_service.choose_map([None])

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        assert chosen_map == (4, "CHOOSE_ME", "maps/choose_me.v001.zip")


async def test_choose_map_all_maps_played(ladder_service: LadderService):
    ladder_service.get_ladder_history = CoroMock(
        return_value=[1, 2, 3]
    )

    ladder_service.game_service.ladder_maps = [
        (1, "some_map", "maps/some_map.v001.zip"),
        (2, "some_map", "maps/some_map.v001.zip"),
        (3, "some_map", "maps/some_map.v001.zip"),
    ]

    chosen_map = await ladder_service.choose_map([None])

    assert chosen_map is not None


async def test_choose_map_raises_on_empty_map_pool(ladder_service: LadderService):
    ladder_service.game_service.ladder_maps = []

    with pytest.raises(RuntimeError):
        await ladder_service.choose_map([])


async def test_get_ladder_history(ladder_service: LadderService, players, db_engine):
    async with db_engine.acquire() as conn:
        await conn.execute(
            game_player_stats.insert().values(gameId=1, playerId=players.hosting.id, AI=False, faction=0, color=0, team=2, place=0, mean=1500, deviation=500, scoreTime=func.now())
        )
    history = await ladder_service.get_ladder_history(players.hosting)

    print(history)
    assert history == [1]


async def test_get_ladder_history_many_maps(ladder_service: LadderService, players, db_engine):
    game_id_start = 41935  # Some arbitrary number
    num_maps = 7
    async with db_engine.acquire() as conn:
        for i in range(num_maps):
            await conn.execute(
                game_stats.insert().values(
                    id=game_id_start+i,
                    startTime=func.now() + text(f"interval {i+1} minute"),
                    gameType='0',
                    gameMod=6,
                    host=players.hosting.id,
                    mapId=i,
                    gameName="MapRepitition",
                    validity=0
                )
            )
            await conn.execute(
                game_player_stats.insert().values(
                    gameId=game_id_start+i,
                    playerId=players.hosting.id,
                    AI=False,
                    faction=0,
                    color=0,
                    team=2,
                    place=0,
                    mean=1500,
                    deviation=500,
                    scoreTime=func.now() + text(f"interval {i+1} minute")
                )
            )

    history = await ladder_service.get_ladder_history(players.hosting)

    assert history == [num_maps-1, num_maps-2, num_maps-3]
