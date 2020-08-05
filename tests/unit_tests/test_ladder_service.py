import asyncio
from unittest import mock

import pytest
from asynctest import CoroutineMock, create_autospec, exhaust_callbacks

from server import GameService, LadderService
from server.db.models import matchmaker_queue, matchmaker_queue_map_pool
from server.games import LadderGame
from server.ladder_service import game_name
from server.matchmaker import MatchmakerQueue
from server.players import PlayerState
from server.types import Map
from tests.utils import fast_forward

pytestmark = pytest.mark.asyncio


async def test_queue_initialization(database, game_service):
    ladder_service = LadderService(database, game_service)

    def make_mock_queue(*args, **kwargs):
        queue = create_autospec(MatchmakerQueue)
        queue.map_pools = {}
        return queue

    with mock.patch("server.ladder_service.MatchmakerQueue", make_mock_queue):
        for name in list(ladder_service.queues.keys()):
            ladder_service.queues[name] = make_mock_queue()

        await ladder_service.initialize()

        for queue in ladder_service.queues.values():
            queue.initialize.assert_called_once()


async def test_load_from_database(ladder_service, queue_factory):
    # Insert some outdated data
    ladder_service.queues["test"] = queue_factory(name="test")

    # Data should be the same on each load
    for _ in range(3):
        await ladder_service.update_data()

        # FIXME: Accounting for hardcoded queues
        assert len(ladder_service.queues) == 2

        queue = ladder_service.queues["ladder1v1"]
        assert queue.name == "ladder1v1"
        assert len(queue.map_pools) == 3
        assert list(ladder_service.ladder_1v1_map_pool.maps.values()) == [
            Map(id=1, name='SCMP_001', path='maps/scmp_001.zip'),
            Map(id=2, name='SCMP_002', path='maps/scmp_002.zip')
        ]


async def test_load_from_database_new_data(ladder_service, database):
    async with database.acquire() as conn:
        result = await conn.execute(matchmaker_queue.insert().values(
            technical_name="test",
            featured_mod_id=1,
            leaderboard_id=1,
            name_key="test.name"
        ))
        await conn.execute(matchmaker_queue_map_pool.insert().values(
            matchmaker_queue_id=result.lastrowid,
            map_pool_id=1
        ))

    await ladder_service.update_data()

    test_queue = ladder_service.queues["test"]

    assert test_queue.name == "test"
    assert test_queue._is_running
    # Queue pop times are 1 second for tests
    test_queue.find_matches = CoroutineMock()
    await asyncio.sleep(1.5)

    test_queue.find_matches.assert_called()


async def test_start_game_1v1(
    ladder_service: LadderService,
    game_service: GameService,
    player_factory,
):
    queue = ladder_service.queues["ladder1v1"]
    p1 = player_factory("Dostya", player_id=1, with_lobby_connection=True)
    p2 = player_factory("Rhiza", player_id=2, with_lobby_connection=True)

    with mock.patch('server.games.game.Game.await_hosted', CoroutineMock()):
        await ladder_service.start_game([p1], [p2], queue)

    game = game_service[game_service.game_id_counter]

    assert p1.lobby_connection.launch_game.called
    assert p2.lobby_connection.launch_game.called
    assert isinstance(game, LadderGame)
    assert game.rating_type == queue.rating_type
    assert game.max_players == 2


@fast_forward(120)
async def test_start_game_timeout(
    ladder_service: LadderService,
    player_factory,
):
    queue = ladder_service.queues["ladder1v1"]
    p1 = player_factory('Dostya', player_id=1, with_lobby_connection=True)
    p2 = player_factory('Rhiza', player_id=2, with_lobby_connection=True)

    await ladder_service.start_game([p1], [p2], queue)

    p1.lobby_connection.send.assert_called_once_with({"command": "match_cancelled"})
    p2.lobby_connection.send.assert_called_once_with({"command": "match_cancelled"})
    assert p1.lobby_connection.launch_game.called
    # TODO: Once client supports `match_cancelled` change this to `assert not ...`
    assert p2.lobby_connection.launch_game.called


async def test_start_game_with_teams(
    ladder_service: LadderService,
    game_service: GameService,
    player_factory,
):
    queue = ladder_service.queues["tmm2v2"]
    p1 = player_factory("Dostya", player_id=1, with_lobby_connection=True)
    p2 = player_factory("Rhiza", player_id=2, with_lobby_connection=True)
    p3 = player_factory("QAI", player_id=3, with_lobby_connection=True)
    p4 = player_factory("Hall", player_id=4, with_lobby_connection=True)

    game_service.ladder_maps = [(1, 'scmp_007', 'maps/scmp_007.zip')]

    with mock.patch('server.games.game.Game.await_hosted', CoroutineMock()):
        await ladder_service.start_game([p1, p3], [p2, p4], queue)

    game = game_service[game_service.game_id_counter]

    assert p1.lobby_connection.launch_game.called
    assert p2.lobby_connection.launch_game.called
    assert p3.lobby_connection.launch_game.called
    assert p4.lobby_connection.launch_game.called
    assert isinstance(game, LadderGame)
    assert game.rating_type == queue.rating_type
    assert game.max_players == 4


async def test_inform_player(ladder_service: LadderService, player_factory):
    p1 = player_factory(
        "Dostya",
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


@pytest.mark.skip("TODO: Add player parties")
async def test_search_info_message(
    ladder_service: LadderService,
    player_factory,
    queue_factory,
    event_loop
):
    ladder_service.queues["tmm2v2"] = queue_factory("tmm2v2")

    p1 = player_factory(
        "Dostya",
        ladder_rating=(1000, 10),
        with_lobby_connection=True
    )
    p1.send_message = CoroutineMock()
    p2 = player_factory(
        "Rhiza",
        ladder_rating=(1000, 10),
        with_lobby_connection=True
    )
    p2.send_message = CoroutineMock()
    search1 = Search([p1, p2])

    await ladder_service.start_search(p1, search1, "ladder1v1")
    await exhaust_callbacks(event_loop)

    msg = {
        "command": "search_info",
        "queue_name": "ladder1v1",
        "state": "start"
    }
    p1.send_message.assert_called_once_with(msg)
    p2.send_message.assert_called_once_with(msg)

    p1.send_message.reset_mock()
    p2.send_message.reset_mock()
    search2 = Search([p1, p2])
    await ladder_service.start_search(p1, search2, "tmm2v2")
    await exhaust_callbacks(event_loop)

    msg = {
        "command": "search_info",
        "queue_name": "tmm2v2",
        "state": "start"
    }
    p1.send_message.assert_called_once_with(msg)
    p2.send_message.assert_called_once_with(msg)

    p1.send_message.reset_mock()
    p2.send_message.reset_mock()
    await ladder_service.cancel_search(p1)
    await exhaust_callbacks(event_loop)

    call_args = [
        mock.call({
            "command": "search_info",
            "queue_name": "ladder1v1",
            "state": "stop"
        }),
        mock.call({
            "command": "search_info",
            "queue_name": "tmm2v2",
            "state": "stop"
        }),
    ]

    assert p1.send_message.call_args_list == call_args
    assert p2.send_message.call_args_list == call_args


async def test_start_search_multiqueue(
    ladder_service: LadderService,
    player_factory,
    queue_factory,
    event_loop
):
    ladder_service.queues["tmm2v2"] = queue_factory("tmm2v2")

    p1 = player_factory(
        "Dostya", ladder_rating=(1000, 10), with_lobby_connection=True
    )

    await ladder_service.start_search(p1, "ladder1v1")
    await exhaust_callbacks(event_loop)

    assert p1 in ladder_service.searches["ladder1v1"]

    await ladder_service.start_search(p1, "tmm2v2")
    await exhaust_callbacks(event_loop)

    assert p1 in ladder_service.searches["ladder1v1"]
    assert p1 in ladder_service.searches["tmm2v2"]

    await ladder_service.cancel_search(p1, "tmm2v2")
    await exhaust_callbacks(event_loop)

    assert p1 in ladder_service.searches["ladder1v1"]
    assert p1 not in ladder_service.searches["tmm2v2"]


async def test_start_and_cancel_search(
    ladder_service: LadderService,
    player_factory,
    event_loop
):
    p1 = player_factory('Dostya', player_id=1, ladder_rating=(1500, 500), ladder_games=0)

    await ladder_service.start_search(p1, 'ladder1v1')
    await exhaust_callbacks(event_loop)
    search = ladder_service.searches["ladder1v1"][p1]

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search in ladder_service.queues['ladder1v1']._queue
    assert not search.is_cancelled

    await ladder_service.cancel_search(p1)

    assert p1.state == PlayerState.IDLE
    assert search.is_cancelled


async def test_start_search_cancels_previous_search(
    ladder_service: LadderService,
    player_factory,
    event_loop
):
    p1 = player_factory(
        'Dostya',
        player_id=1,
        ladder_rating=(1500, 500),
        ladder_games=0,
        with_lobby_connection=True
    )

    await ladder_service.start_search(p1, 'ladder1v1')
    await exhaust_callbacks(event_loop)
    search1 = ladder_service.searches["ladder1v1"][p1]

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search1 in ladder_service.queues['ladder1v1']._queue

    await ladder_service.start_search(p1, 'ladder1v1')
    await exhaust_callbacks(event_loop)
    search2 = ladder_service.searches["ladder1v1"][p1]

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search1.is_cancelled
    assert search1 not in ladder_service.queues['ladder1v1']._queue
    assert search2 in ladder_service.queues['ladder1v1']._queue


async def test_cancel_all_searches(ladder_service: LadderService,
                                   player_factory, event_loop):
    p1 = player_factory(login="Dostya", player_id=1, ladder_rating=(1500, 500), ladder_games=0)

    await ladder_service.start_search(p1, 'ladder1v1')
    await exhaust_callbacks(event_loop)
    search = ladder_service.searches["ladder1v1"][p1]

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search in ladder_service.queues['ladder1v1']._queue
    assert not search.is_cancelled

    await ladder_service.cancel_search(p1)

    assert p1.state == PlayerState.IDLE
    assert search.is_cancelled
    assert p1 not in ladder_service.searches['ladder1v1']


async def test_cancel_twice(ladder_service: LadderService, player_factory):
    p1 = player_factory(login="Dostya", player_id=1, ladder_rating=(1500, 500), ladder_games=0)
    p2 = player_factory(login="Brackman", player_id=2, ladder_rating=(2000, 500), ladder_games=0)

    await ladder_service.start_search(p1, 'ladder1v1')
    search = ladder_service.searches["ladder1v1"][p1]
    await ladder_service.start_search(p2, 'ladder1v1')
    search2 = ladder_service.searches["ladder1v1"][p2]

    searches = ladder_service._cancel_existing_searches(p1)
    assert search.is_cancelled
    assert searches == [("ladder1v1", search)]
    assert not search2.is_cancelled

    searches = ladder_service._cancel_existing_searches(p1)
    assert searches == []

    searches = ladder_service._cancel_existing_searches(p2)
    assert search2.is_cancelled
    assert searches == [("ladder1v1", search2)]


@fast_forward(5)
async def test_start_game_called_on_match(ladder_service: LadderService, player_factory):
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

    await ladder_service.start_search(p1, 'ladder1v1')
    await ladder_service.start_search(p2, 'ladder1v1')

    await asyncio.sleep(2)

    ladder_service.inform_player.assert_called()
    ladder_service.start_game.assert_called_once()


@pytest.mark.parametrize("ratings", (
    (((1500, 500), 0), ((1000, 100), 1000)),
    (((1500, 500), 0), ((300, 100), 1000)),
    (((400, 100), 10), ((300, 100), 1000))
))
async def test_start_game_map_selection_newbie_pool(
    ladder_service: LadderService,
    player_factory,
    ratings
):
    p1 = player_factory(
        ladder_rating=ratings[0][0],
        ladder_games=ratings[0][1],
    )
    p2 = player_factory(
        ladder_rating=ratings[1][0],
        ladder_games=ratings[1][1],
    )

    queue = ladder_service.queues["ladder1v1"]
    queue.map_pools.clear()
    newbie_map_pool = mock.Mock()
    full_map_pool = mock.Mock()
    queue.add_map_pool(newbie_map_pool, None, 500)
    queue.add_map_pool(full_map_pool, 500, None)

    await ladder_service.start_game([p1], [p2], queue)

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

    await ladder_service.start_game([p1], [p2], queue)

    newbie_map_pool.choose_map.assert_not_called()
    full_map_pool.choose_map.assert_called_once()


async def test_get_ladder_history(ladder_service: LadderService, players):
    history = await ladder_service.get_game_history(
        [players.hosting],
        mod="ladder1v1",
        limit=1
    )

    assert history == [6]


async def test_get_ladder_history_many_maps(ladder_service: LadderService, players):
    history = await ladder_service.get_game_history(
        [players.hosting],
        mod="ladder1v1",
        limit=4
    )

    assert history == [6, 5, 4, 3]


async def test_get_ladder_history_1v1(ladder_service: LadderService, player_factory):
    p1 = player_factory("Dostya", player_id=1)
    p2 = player_factory("Rhiza", player_id=2)

    history = await ladder_service.get_game_history(
        [p1, p2],
        mod="ladder1v1",
    )

    assert history == [6, 5, 4, 3, 4, 5]


async def test_game_name(player_factory):
    p1 = player_factory(login="Dostya", clan="CYB")
    p2 = player_factory(login="QAI", clan="CYB")
    p3 = player_factory(login="Rhiza", clan="AEO")
    p4 = player_factory(login="Burke", clan="AEO")

    assert game_name([p1, p2], [p3, p4]) == "Team CYB Vs Team AEO"


async def test_game_name_conflicting(player_factory):
    p1 = player_factory(login="Dostya", clan="CYB")
    p2 = player_factory(login="QAI", clan="CYB")
    p3 = player_factory(login="Rhiza", clan="AEO")
    p4 = player_factory(login="Hall", clan="UEF")

    assert game_name([p1, p2], [p3, p4]) == "Team CYB Vs Team Rhiza"


async def test_game_name_no_clan(player_factory):
    p1 = player_factory(login="Dostya", clan=None)
    p2 = player_factory(login="QAI", clan="CYB")
    p3 = player_factory(login="Rhiza", clan=None)
    p4 = player_factory(login="Burke", clan=None)

    assert game_name([p1, p2], [p3, p4]) == "Team Dostya Vs Team Rhiza"


async def test_game_name_1v1(player_factory):
    p1 = player_factory(login="Dostya", clan="CYB")
    p2 = player_factory(login="Rhiza", clan=None)

    assert game_name([p1], [p2]) == "Dostya Vs Rhiza"


async def test_game_name_uneven(player_factory):
    p1 = player_factory(login="Dostya", clan="CYB")
    p2 = player_factory(login="QAI", clan="CYB")
    p3 = player_factory(login="Rhiza", clan=None)

    assert game_name([p1, p2], [p3]) == "Team CYB Vs Rhiza"


async def test_game_name_many_teams(player_factory):
    p1 = player_factory(login="Dostya", clan="CYB")
    p2 = player_factory(login="QAI", clan="CYB")
    p3 = player_factory(login="Rhiza", clan=None)
    p4 = player_factory(login="Kale", clan=None)

    assert game_name([p1], [p2], [p3], [p4]) == "Dostya Vs QAI Vs Rhiza Vs Kale"


async def test_inform_player_message(
    ladder_service: LadderService,
    player_factory
):
    player = player_factory(ladder_rating=(1500, 500))
    player.send_message = CoroutineMock()

    await ladder_service.inform_player(player)

    player.send_message.assert_called_once_with({
        "command": "notice",
        "style": "info",
        "text": (
            "<i>Welcome to the matchmaker</i><br><br><b>Until "
            "you've played enough games for the system to learn "
            "your skill level, you'll be matched randomly.</b><br>"
            "Afterwards, you'll be more reliably matched up with "
            "people of your skill level: so don't worry if your "
            "first few games are uneven. This will improve as you "
            "play!</b>"
        )
    })


async def test_inform_player_message_2(
    ladder_service: LadderService,
    player_factory
):
    player = player_factory(ladder_rating=(1500, 400.1235))
    player.send_message = CoroutineMock()

    await ladder_service.inform_player(player)

    player.send_message.assert_called_once_with({
        "command": "notice",
        "style": "info",
        "text": (
            "The system is still learning you.<b><br><br>"
            "The learning phase is 40% complete<b>"
        )
    })
