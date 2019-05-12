import asyncio
from unittest import mock

import pytest
from server import GameService, LadderService
from server.matchmaker import Search
from server.players import Player, PlayerState
from tests import CoroMock


async def test_start_game(ladder_service: LadderService, game_service: GameService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p2 = mock.create_autospec(Player('Rhiza', id=2))

    p1.id = 1
    p2.id = 2
    game_service.ladder_maps = [(1, 'scmp_007', 'maps/scmp_007.zip')]

    with mock.patch('server.games.game.Game.await_hosted', CoroMock()):
        await ladder_service.start_game(p1, p2)

    assert p1.lobby_connection.launch_game.called
    assert p2.lobby_connection.launch_game.called


async def test_start_game_timeout(ladder_service: LadderService, game_service: GameService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p2 = mock.create_autospec(Player('Rhiza', id=2))

    p1.id = 1
    p2.id = 2
    game_service.ladder_maps = [(1, 'scmp_007', 'maps/scmp_007.zip')]

    with mock.patch('server.games.game.Game.sleep', CoroMock()):
        await ladder_service.start_game(p1, p2)

    p1.lobby_connection.send.assert_called_once_with({"command": "game_launch_timeout"})
    p2.lobby_connection.send.assert_called_once_with({"command": "game_launch_timeout"})
    assert p1.lobby_connection.launch_game.called
    # TODO: Once client supports `game_launch_timeout` change this to `assert not ...`
    assert p2.lobby_connection.launch_game.called


def test_inform_player(ladder_service: LadderService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p1.ladder_rating = (1500, 500)

    ladder_service.inform_player(p1)

    assert p1.lobby_connection.sendJSON.called


async def test_start_and_cancel_search(ladder_service: LadderService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p1.ladder_rating = (1500, 500)
    p1.numGames = 0

    search = Search([p1])

    ladder_service.start_search(p1, search, 'ladder1v1')
    await asyncio.sleep(0)  # Give the other coro a chance to run

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert ladder_service.queues['ladder1v1'].queue[search]
    assert not search.is_cancelled

    ladder_service.cancel_search(p1)

    assert p1.state == PlayerState.IDLE
    assert search.is_cancelled


async def test_start_search_cancels_previous_search(ladder_service: LadderService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p1.ladder_rating = (1500, 500)
    p1.numGames = 0

    search1 = Search([p1])

    ladder_service.start_search(p1, search1, 'ladder1v1')
    await asyncio.sleep(0)  # Give the other coro a chance to run

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert ladder_service.queues['ladder1v1'].queue[search1]

    search2 = Search([p1])

    ladder_service.start_search(p1, search2, 'ladder1v1')
    await asyncio.sleep(0)  # Give the other coro a chance to run

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search1.is_cancelled
    assert not ladder_service.queues['ladder1v1'].queue.get(search1)
    assert ladder_service.queues['ladder1v1'].queue[search2]


async def test_cancel_all_searchs(ladder_service: LadderService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p1.ladder_rating = (1500, 500)
    p1.numGames = 0

    search = Search([p1])

    ladder_service.start_search(p1, search, 'ladder1v1')
    await asyncio.sleep(0)  # Give the other coro a chance to run

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert ladder_service.queues['ladder1v1'].queue[search]
    assert not search.is_cancelled

    ladder_service.cancel_search(p1)

    assert p1.state == PlayerState.IDLE
    assert search.is_cancelled
    assert p1 not in ladder_service.searches['ladder1v1']


async def test_cancel_twice(ladder_service: LadderService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p1.ladder_rating = (1500, 500)
    p1.numGames = 0

    p2 = mock.create_autospec(Player('Brackman', id=1))
    p2.ladder_rating = (2000, 50)
    p2.numGames = 0

    search = Search([p1])
    search2 = Search([p2])

    ladder_service.start_search(p1, search, 'ladder1v1')
    ladder_service.start_search(p2, search2, 'ladder1v1')

    searches = ladder_service._cancel_existing_searches(p1)
    assert search.is_cancelled
    assert searches == [search]
    assert not search2.is_cancelled

    searches = ladder_service._cancel_existing_searches(p1)
    assert searches == []

    searches = ladder_service._cancel_existing_searches(p2)
    assert search2.is_cancelled
    assert searches == [search2]


async def test_start_game_called_on_match(ladder_service: LadderService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p1.ladder_rating = (2300, 64)
    p1.numGames = 0

    p2 = mock.create_autospec(Player('QAI', id=4))
    p2.ladder_rating = (2350, 125)
    p2.numGames = 0

    ladder_service.start_game = CoroMock()
    ladder_service.inform_player = mock.Mock()

    ladder_service.start_search(p1, Search([p1]), 'ladder1v1')
    ladder_service.start_search(p2, Search([p2]), 'ladder1v1')

    await asyncio.sleep(1)

    ladder_service.inform_player.assert_called()
    ladder_service.start_game.assert_called_once()


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
    history = await ladder_service.get_ladder_history(players.hosting, limit=1)
    assert history == [6]


async def test_get_ladder_history_many_maps(ladder_service: LadderService, players, db_engine):
    history = await ladder_service.get_ladder_history(players.hosting, limit=4)
    assert history == [6, 5, 4, 3]
