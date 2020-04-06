import asyncio
from unittest import mock

import pytest
from asynctest import CoroutineMock, exhaust_callbacks
from server import LadderService
from server.matchmaker import Search
from server.players import PlayerState
from tests.utils import fast_forward

pytestmark = pytest.mark.asyncio


async def test_load_from_database(ladder_service):
    # Data should be the same on each load
    for _ in range(3):
        await ladder_service.update_data()

        assert len(ladder_service.queues) == 1

        queue = ladder_service.queues["ladder1v1"]
        assert queue.name == "ladder1v1"
        assert len(queue.map_pools) == 3


async def test_start_game(ladder_service: LadderService, player_factory):
    p1 = player_factory('Dostya', player_id=1, with_lobby_connection=True)
    p2 = player_factory('Rhiza', player_id=2, with_lobby_connection=True)

    with mock.patch('server.games.game.Game.await_hosted', CoroutineMock()):
        await ladder_service.start_game(p1, p2)

    assert p1.lobby_connection.launch_game.called
    assert p2.lobby_connection.launch_game.called


@fast_forward(120)
async def test_start_game_timeout(ladder_service: LadderService, player_factory):
    p1 = player_factory('Dostya', player_id=1, with_lobby_connection=True)
    p2 = player_factory('Rhiza', player_id=2, with_lobby_connection=True)

    await ladder_service.start_game(p1, p2)

    p1.lobby_connection.send.assert_called_once_with({"command": "game_launch_cancelled"})
    p2.lobby_connection.send.assert_called_once_with({"command": "game_launch_cancelled"})
    assert p1.lobby_connection.launch_game.called
    # TODO: Once client supports `game_launch_cancelled` change this to `assert not ...`
    assert p2.lobby_connection.launch_game.called


async def test_inform_player(ladder_service: LadderService, player_factory):
    p1 = player_factory(
        'Dostya',
        player_id=1,
        ladder_rating=(1500, 500),
        with_lobby_connection=True
    )

    await ladder_service.inform_player(p1)

    # Message is sent after the first call
    p1.lobby_connection.send.assert_called_once()
    await ladder_service.inform_player(p1)
    p1.lobby_connection.send.reset_mock()
    # But not after the second
    p1.lobby_connection.send.assert_not_called()
    await ladder_service.on_connection_lost(p1)
    await ladder_service.inform_player(p1)

    # But it is called if the player relogs
    p1.lobby_connection.send.assert_called_once()


async def test_start_and_cancel_search(ladder_service: LadderService,
                                       player_factory, event_loop):
    p1 = player_factory('Dostya', player_id=1, ladder_rating=(1500, 500), ladder_games=0)

    search = Search([p1])

    await ladder_service.start_search(p1, search, 'ladder1v1')
    await exhaust_callbacks(event_loop)

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert ladder_service.queues['ladder1v1'].queue[search]
    assert not search.is_cancelled

    await ladder_service.cancel_search(p1)

    assert p1.state == PlayerState.IDLE
    assert search.is_cancelled


async def test_start_search_cancels_previous_search(
        ladder_service: LadderService, player_factory, event_loop):
    p1 = player_factory('Dostya', player_id=1, ladder_rating=(1500, 500), ladder_games=0)

    search1 = Search([p1])

    await ladder_service.start_search(p1, search1, 'ladder1v1')
    await exhaust_callbacks(event_loop)

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert ladder_service.queues['ladder1v1'].queue[search1]

    search2 = Search([p1])

    await ladder_service.start_search(p1, search2, 'ladder1v1')
    await exhaust_callbacks(event_loop)

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search1.is_cancelled
    assert not ladder_service.queues['ladder1v1'].queue.get(search1)
    assert ladder_service.queues['ladder1v1'].queue[search2]


async def test_cancel_all_searches(ladder_service: LadderService,
                                   player_factory, event_loop):
    p1 = player_factory('Dostya', player_id=1, ladder_rating=(1500, 500), ladder_games=0)

    search = Search([p1])

    await ladder_service.start_search(p1, search, 'ladder1v1')
    await exhaust_callbacks(event_loop)

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert ladder_service.queues['ladder1v1'].queue[search]
    assert not search.is_cancelled

    await ladder_service.cancel_search(p1)

    assert p1.state == PlayerState.IDLE
    assert search.is_cancelled
    assert p1 not in ladder_service.searches['ladder1v1']


async def test_cancel_twice(ladder_service: LadderService, player_factory):
    p1 = player_factory('Dostya', player_id=1, ladder_rating=(1500, 500), ladder_games=0)
    p2 = player_factory('Brackman', player_id=2, ladder_rating=(2000, 500), ladder_games=0)

    search = Search([p1])
    search2 = Search([p2])

    await ladder_service.start_search(p1, search, 'ladder1v1')
    await ladder_service.start_search(p2, search2, 'ladder1v1')

    searches = ladder_service._cancel_existing_searches(p1)
    assert search.is_cancelled
    assert searches == [search]
    assert not search2.is_cancelled

    searches = ladder_service._cancel_existing_searches(p1)
    assert searches == []

    searches = ladder_service._cancel_existing_searches(p2)
    assert search2.is_cancelled
    assert searches == [search2]


@fast_forward(5)
async def test_start_game_called_on_match(
    ladder_service: LadderService, player_factory
):
    p1 = player_factory(
        'Dostya',
        player_id=1,
        ladder_rating=(2300, 64),
        ladder_games=0,
        with_lobby_connection=True
    )
    p2 = player_factory(
        'QAI',
        player_id=2,
        ladder_rating=(2350, 125),
        ladder_games=0,
        with_lobby_connection=True
    )

    ladder_service.start_game = CoroutineMock()
    ladder_service.inform_player = CoroutineMock()

    await ladder_service.start_search(p1, Search([p1]), 'ladder1v1')
    await ladder_service.start_search(p2, Search([p2]), 'ladder1v1')

    await asyncio.sleep(2)

    ladder_service.inform_player.assert_called()
    ladder_service.start_game.assert_called_once()


async def test_start_game_map_selection(
    ladder_service: LadderService, player_factory
):
    p1 = player_factory(
        ladder_rating=(1500, 500),
        ladder_games=0,
    )
    p2 = player_factory(
        ladder_rating=(1000, 100),
        ladder_games=1000,
    )

    queue = ladder_service.queues["ladder1v1"]
    queue.map_pools.clear()
    newbie_map_pool = mock.Mock()
    full_map_pool = mock.Mock()
    queue.add_map_pool(newbie_map_pool, None, 500)
    queue.add_map_pool(full_map_pool, 500, None)

    await ladder_service.start_game(p1, p2)

    newbie_map_pool.choose_map.assert_not_called()
    full_map_pool.choose_map.assert_called_once()


async def test_start_game_map_selection_newbies(
    ladder_service: LadderService, player_factory
):
    p1 = player_factory(
        ladder_rating=(1500, 500),
        ladder_games=0,
    )
    p2 = player_factory(
        ladder_rating=(300, 100),
        ladder_games=1000,
    )

    queue = ladder_service.queues["ladder1v1"]
    queue.map_pools.clear()
    newbie_map_pool = mock.Mock()
    full_map_pool = mock.Mock()
    queue.add_map_pool(newbie_map_pool, None, 500)
    queue.add_map_pool(full_map_pool, 500, None)

    await ladder_service.start_game(p1, p2)

    newbie_map_pool.choose_map.assert_called_once()
    full_map_pool.choose_map.assert_not_called()


async def test_start_game_map_selection_pros(
    ladder_service: LadderService, player_factory
):
    p1 = player_factory(
        ladder_rating=(2000, 50),
        ladder_games=1000,
    )
    p2 = player_factory(
        ladder_rating=(1500, 100),
        ladder_games=1000,
    )

    queue = ladder_service.queues["ladder1v1"]
    queue.map_pools.clear()
    newbie_map_pool = mock.Mock()
    full_map_pool = mock.Mock()
    queue.add_map_pool(newbie_map_pool, None, 500)
    queue.add_map_pool(full_map_pool, 500, None)

    await ladder_service.start_game(p1, p2)

    newbie_map_pool.choose_map.assert_not_called()
    full_map_pool.choose_map.assert_called_once()


async def test_get_ladder_history(ladder_service: LadderService, players, database):
    history = await ladder_service.get_game_history(
        players.hosting,
        mod="ladder1v1",
        limit=1
    )

    assert history == [6]


async def test_get_ladder_history_many_maps(ladder_service: LadderService, players, database):
    history = await ladder_service.get_game_history(
        players.hosting,
        mod="ladder1v1",
        limit=4
    )

    assert history == [6, 5, 4, 3]
