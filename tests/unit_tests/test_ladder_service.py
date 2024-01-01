import asyncio
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from server import LadderService
from server.db.models import matchmaker_queue, matchmaker_queue_map_pool
from server.exceptions import DisabledError
from server.games import LadderGame
from server.games.ladder_game import GameClosedError
from server.ladder_service import game_name
from server.matchmaker import MapPool, MatchmakerQueue
from server.players import PlayerState
from server.rating import RatingType
from server.types import Map, NeroxisGeneratedMap
from tests.conftest import make_player
from tests.utils import autocontext, exhaust_callbacks, fast_forward

from .strategies import st_players


async def test_queue_initialization(database, game_service, violation_service):
    ladder_service = LadderService(database, game_service, violation_service)

    def make_mock_queue(*args, **kwargs):
        queue = mock.create_autospec(MatchmakerQueue)
        queue.map_pools = {}
        return queue

    with mock.patch(
        "server.ladder_service.ladder_service.MatchmakerQueue",
        make_mock_queue
    ):
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

        assert len(ladder_service.queues) == 4

        queue = ladder_service.queues["ladder1v1"]
        assert queue.name == "ladder1v1"
        assert queue.get_game_options() is None
        assert queue.rating_type == "ladder_1v1"
        assert queue.rating_peak == 1000.0
        assert len(queue.map_pools) == 3
        assert list(queue.map_pools[1][0].maps.values()) == [
            Map(15, "scmp_015", ranked=True),
            Map(16, "scmp_015.v0002", ranked=True),
            Map(17, "scmp_015.v0003", ranked=True),
        ]
        assert list(queue.map_pools[2][0].maps.values()) == [
            Map(11, "scmp_011", ranked=True),
            Map(14, "scmp_014", ranked=True),
            Map(15, "scmp_015", ranked=True),
            Map(16, "scmp_015.v0002", ranked=True),
            Map(17, "scmp_015.v0003", ranked=True),
        ]
        assert list(queue.map_pools[3][0].maps.values()) == [
            Map(1, "scmp_001", ranked=True),
            Map(2, "scmp_002", ranked=True),
            Map(3, "scmp_003", ranked=True),
        ]

        queue = ladder_service.queues["neroxis1v1"]
        assert queue.name == "neroxis1v1"
        assert len(queue.map_pools) == 1
        assert list(queue.map_pools[4][0].maps.values()) == [
            NeroxisGeneratedMap.of({
                "version": "0.0.0",
                "spawns": 2,
                "size": 512,
                "type": "neroxis"
            }),
            NeroxisGeneratedMap.of({
                "version": "0.0.0",
                "spawns": 2,
                "size": 768,
                "type": "neroxis"
            }),
        ]

        queue = ladder_service.queues["tmm2v2"]
        assert queue.rating_type == "tmm_2v2"
        assert queue.rating_peak == 1100.0

        queue = ladder_service.queues["gameoptions"]
        assert queue.rating_type == "global"
        assert queue.rating_peak == 500.0
        assert queue.get_game_options() == {
            "Share": "ShareUntilDeath",
            "UnitCap": 500
        }


@fast_forward(5)
async def test_load_from_database_new_data(ladder_service, database):
    async with database.acquire() as conn:
        await conn.execute(matchmaker_queue.insert().values(
            id=1000000,
            technical_name="test",
            featured_mod_id=1,
            leaderboard_id=1,
            name_key="test.name"
        ))
        await conn.execute(matchmaker_queue_map_pool.insert().values(
            matchmaker_queue_id=1000000,
            map_pool_id=1
        ))

    await ladder_service.update_data()

    test_queue = ladder_service.queues["test"]

    assert test_queue.name == "test"
    assert test_queue._is_running
    # Queue pop times are 1 second for tests
    test_queue.find_matches = mock.AsyncMock()
    await asyncio.sleep(1.5)

    test_queue.find_matches.assert_called()


@given(
    player1=st_players("p1", player_id=1, lobby_connection_spec="mock"),
    player2=st_players("p2", player_id=2, lobby_connection_spec="mock")
)
@settings(deadline=None)
@autocontext("ladder_and_game_service_context", "monkeypatch_context")
async def test_start_game_1v1(
    ladder_and_game_service,
    monkeypatch,
    player1,
    player2
):
    ladder_service, game_service = ladder_and_game_service
    queue = ladder_service.queues["ladder1v1"]

    monkeypatch.setattr(LadderGame, "wait_hosted", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "wait_launched", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "timeout_game", mock.AsyncMock())

    await ladder_service.start_game([player1], [player2], queue)

    game = game_service[game_service.game_id_counter]

    assert player1.lobby_connection.write_launch_game.called
    # TODO: Once client supports `match_cancelled` change this to `assert not`
    assert player2.lobby_connection.write_launch_game.called
    assert isinstance(game, LadderGame)
    assert game.rating_type == queue.rating_type
    assert game.max_players == 2

    LadderGame.wait_launched.assert_called_once()


async def test_start_game_with_game_options(
    ladder_service,
    game_service,
    monkeypatch,
    player_factory
):
    queue = ladder_service.queues["gameoptions"]
    p1 = player_factory("Dostya", player_id=1, lobby_connection_spec="auto")
    p2 = player_factory("Rhiza", player_id=2, lobby_connection_spec="auto")

    monkeypatch.setattr(LadderGame, "wait_hosted", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "wait_launched", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "timeout_game", mock.AsyncMock())

    # We're cheating a little bit here for simplicity of the test. The queue
    # is actually set up to be 3v3 but `start_game` doesn't care.
    await ladder_service.start_game([p1], [p2], queue)

    game = game_service[game_service.game_id_counter]

    assert game.rating_type == queue.rating_type
    assert game.max_players == 2
    assert game.game_options["Share"] == "ShareUntilDeath"
    assert game.game_options["UnitCap"] == 500

    LadderGame.wait_launched.assert_called_once()


@fast_forward(65)
async def test_start_game_timeout(
    ladder_service: LadderService,
    player_factory,
    monkeypatch
):
    queue = ladder_service.queues["ladder1v1"]
    p1 = player_factory("Dostya", player_id=1, lobby_connection_spec="auto")
    p2 = player_factory("Rhiza", player_id=2, lobby_connection_spec="auto")

    monkeypatch.setattr(LadderGame, "timeout_game", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "on_game_finish", mock.AsyncMock())

    await ladder_service.start_game([p1], [p2], queue)

    LadderGame.timeout_game.assert_called_once()
    LadderGame.on_game_finish.assert_called()
    p1_calls = [
        mock.call({
            "command": "match_cancelled",
            "game_id": 41956
        }),
        mock.call({
            "command": "search_violation",
            "count": 1,
            "time": mock.ANY
        }),
        mock.call({
            "command": "notice",
            "style": "info",
            "text": (
                "You have caused a matchmaking connection failure 1 time(s). "
                "Multiple failures result in temporary time-outs from matchmaker. "
                "Please seek support on the forums or discord for persistent issues."
            )
        })
    ]
    p1.lobby_connection.write.assert_has_calls(p1_calls)
    p2.lobby_connection.write.assert_called_once_with({
        "command": "match_cancelled",
        "game_id": 41956
    })
    assert p1.lobby_connection.write_launch_game.called
    # TODO: Once client supports `match_cancelled` change this to `assert not`
    assert p2.lobby_connection.write_launch_game.called
    assert p1.state is PlayerState.IDLE
    assert p2.state is PlayerState.IDLE


@fast_forward(200)
async def test_start_game_timeout_on_send(
    ladder_service: LadderService,
    player_factory,
    monkeypatch
):
    queue = ladder_service.queues["ladder1v1"]
    p1 = player_factory("Dostya", player_id=1, lobby_connection_spec="auto")
    p2 = player_factory("Rhiza", player_id=2, lobby_connection_spec="auto")

    monkeypatch.setattr(LadderGame, "timeout_game", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "on_game_finish", mock.AsyncMock())

    async def wait_forever(*args, **kwargs):
        await asyncio.sleep(1000)
    # Even though launch_game isn't called by start_game, these mocks are
    # important for the test in case someone refactors the code to call it.
    p1.lobby_connection.launch_game.side_effect = wait_forever
    p2.lobby_connection.launch_game.side_effect = wait_forever

    await asyncio.wait_for(
        ladder_service.start_game([p1], [p2], queue),
        timeout=150
    )

    LadderGame.timeout_game.assert_called_once()
    LadderGame.on_game_finish.assert_called()
    p1_calls = [
        mock.call({
            "command": "match_cancelled",
            "game_id": 41956
        }),
        mock.call({
            "command": "search_violation",
            "count": 1,
            "time": mock.ANY
        }),
        mock.call({
            "command": "notice",
            "style": "info",
            "text": (
                "You have caused a matchmaking connection failure 1 time(s). "
                "Multiple failures result in temporary time-outs from matchmaker. "
                "Please seek support on the forums or discord for persistent issues."
            )
        })
    ]
    p1.lobby_connection.write.assert_has_calls(p1_calls)
    p2.lobby_connection.write.assert_called_once_with({
        "command": "match_cancelled",
        "game_id": 41956
    })
    assert p1.lobby_connection.write_launch_game.called


async def test_start_game_game_closed_by_guest(
    ladder_service: LadderService,
    player_factory,
    monkeypatch
):
    queue = ladder_service.queues["ladder1v1"]
    p1 = player_factory("Dostya", player_id=1, lobby_connection_spec="auto")
    p2 = player_factory("Rhiza", player_id=2, lobby_connection_spec="auto")

    monkeypatch.setattr(LadderGame, "wait_hosted", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "timeout_game", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "wait_launched", mock.AsyncMock(side_effect=GameClosedError))
    monkeypatch.setattr(LadderGame, "on_game_finish", mock.AsyncMock())

    await ladder_service.start_game([p1], [p2], queue)

    LadderGame.on_game_finish.assert_called()
    p1.lobby_connection.write.assert_called_once_with({
        "command": "match_cancelled",
        "game_id": 41956
    })
    p2.lobby_connection.write.assert_called_once_with({
        "command": "match_cancelled",
        "game_id": 41956
    })
    assert p1.lobby_connection.write_launch_game.called
    assert p2.lobby_connection.write_launch_game.called
    assert p1.state is PlayerState.IDLE
    assert p2.state is PlayerState.IDLE


async def test_start_game_game_closed_by_host(
    ladder_service: LadderService,
    player_factory,
    monkeypatch
):
    queue = ladder_service.queues["ladder1v1"]
    p1 = player_factory("Dostya", player_id=1, lobby_connection_spec="auto")
    p2 = player_factory("Rhiza", player_id=2, lobby_connection_spec="auto")

    monkeypatch.setattr(LadderGame, "wait_hosted", mock.AsyncMock(side_effect=GameClosedError))
    monkeypatch.setattr(LadderGame, "timeout_game", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "wait_launched", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "on_game_finish", mock.AsyncMock())

    await ladder_service.start_game([p1], [p2], queue)

    LadderGame.on_game_finish.assert_called()
    p1.lobby_connection.write.assert_called_once_with({
        "command": "match_cancelled",
        "game_id": 41956
    })
    p2.lobby_connection.write.assert_called_once_with({
        "command": "match_cancelled",
        "game_id": 41956
    })
    assert p1.lobby_connection.write_launch_game.called
    # TODO: Once client supports `match_cancelled` change this to `assert not`
    assert p2.lobby_connection.write_launch_game.called
    assert p1.state is PlayerState.IDLE
    assert p2.state is PlayerState.IDLE


@given(
    player1=st_players("p1", player_id=1, lobby_connection_spec="mock"),
    player2=st_players("p2", player_id=2, lobby_connection_spec="mock"),
    player3=st_players("p3", player_id=3, lobby_connection_spec="mock"),
    player4=st_players("p4", player_id=4, lobby_connection_spec="mock")
)
@settings(deadline=None)
@autocontext("ladder_and_game_service_context", "monkeypatch_context")
async def test_start_game_with_teams(
    ladder_and_game_service,
    monkeypatch,
    player1,
    player2,
    player3,
    player4
):
    ladder_service, game_service = ladder_and_game_service
    queue = ladder_service.queues["tmm2v2"]

    monkeypatch.setattr(LadderGame, "wait_hosted", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "wait_launched", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "timeout_game", mock.AsyncMock())

    await ladder_service.start_game(
        [player1, player3],
        [player2, player4],
        queue
    )

    game = game_service[game_service.game_id_counter]

    assert player1.lobby_connection.write_launch_game.called
    assert player2.lobby_connection.write_launch_game.called
    assert player3.lobby_connection.write_launch_game.called
    assert player4.lobby_connection.write_launch_game.called
    assert isinstance(game, LadderGame)
    assert game.rating_type == queue.rating_type
    assert game.max_players == 4

    LadderGame.wait_launched.assert_called_once()


@given(
    team1=st.lists(
        st.sampled_from((
            make_player("p1", player_id=1, global_rating=(500, 10)),
            make_player("p3", player_id=3, global_rating=(1000, 10)),
            make_player("p5", player_id=5, global_rating=(2000, 10))
        )),
        min_size=3,
        max_size=3,
        unique=True
    ),
    team2=st.lists(
        st.sampled_from((
            make_player("p2", player_id=2, global_rating=(500, 10)),
            make_player("p4", player_id=4, global_rating=(1000, 10)),
            make_player("p6", player_id=6, global_rating=(2000, 10))
        )),
        min_size=3,
        max_size=3,
        unique=True
    )
)
@settings(deadline=None)
@autocontext("ladder_and_game_service_context", "monkeypatch_context")
async def test_start_game_start_spots(
    ladder_and_game_service,
    monkeypatch,
    queue_factory,
    team1,
    team2
):
    ladder_service, game_service = ladder_and_game_service
    queue = queue_factory(
        "test_3v3",
        mod="faf",
        team_size=3,
        rating_type=RatingType.GLOBAL
    )
    queue.add_map_pool(
        MapPool(1, "test", [Map(1, "scmp_007")]),
        min_rating=None,
        max_rating=None
    )

    monkeypatch.setattr(LadderGame, "wait_hosted", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "wait_launched", mock.AsyncMock())
    await ladder_service.start_game(team1, team2, queue)

    game = game_service[game_service.game_id_counter]

    def get_start_spot(player_id) -> int:
        return game.get_player_option(player_id, "StartSpot")

    assert get_start_spot(1) == get_start_spot(2) - 1
    assert get_start_spot(3) == get_start_spot(4) - 1
    assert get_start_spot(5) == get_start_spot(6) - 1


async def test_write_rating_progress(ladder_service: LadderService, player_factory):
    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1500, 500),
        lobby_connection_spec="auto"
    )

    ladder_service.write_rating_progress(p1, RatingType.LADDER_1V1)
    # Message is sent after the first call
    p1.lobby_connection.write.assert_called_once()

    ladder_service.write_rating_progress(p1, RatingType.LADDER_1V1)
    p1.lobby_connection.write.reset_mock()
    # But not after the second
    p1.lobby_connection.write.assert_not_called()

    ladder_service.on_connection_lost(p1.lobby_connection)
    ladder_service.write_rating_progress(p1, RatingType.LADDER_1V1)
    # But it is called if the player relogs
    p1.lobby_connection.write.assert_called_once()


async def test_search_info_message(
    ladder_service: LadderService,
    player_factory,
    queue_factory,
):
    ladder_service.queues["tmm2v2"] = queue_factory("tmm2v2")

    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1000, 10)
    )
    p1.write_message = mock.Mock()
    p2 = player_factory(
        "Rhiza",
        player_id=2,
        ladder_rating=(1000, 10)
    )
    p2.write_message = mock.Mock()

    ladder_service.start_search([p1, p2], "ladder1v1")

    msg = {
        "command": "search_info",
        "queue_name": "ladder1v1",
        "state": "start"
    }
    p1.write_message.assert_called_once_with(msg)
    p2.write_message.assert_called_once_with(msg)

    p1.write_message.reset_mock()
    p2.write_message.reset_mock()

    ladder_service.start_search([p1, p2], "tmm2v2")

    msg = {
        "command": "search_info",
        "queue_name": "tmm2v2",
        "state": "start"
    }
    p1.write_message.assert_called_once_with(msg)
    p2.write_message.assert_called_once_with(msg)

    p1.write_message.reset_mock()
    p2.write_message.reset_mock()
    ladder_service.cancel_search(p1)

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

    assert p1.write_message.call_args_list == call_args
    assert p2.write_message.call_args_list == call_args


async def test_start_search_multiqueue(
    ladder_service: LadderService,
    player_factory,
    queue_factory,
):
    ladder_service.queues["tmm2v2"] = queue_factory("tmm2v2")

    p1 = player_factory("Dostya", ladder_rating=(1000, 10))

    ladder_service.start_search([p1], "ladder1v1")

    assert "ladder1v1" in ladder_service._searches[p1]

    ladder_service.start_search([p1], "tmm2v2")

    assert "ladder1v1" in ladder_service._searches[p1]
    assert "tmm2v2" in ladder_service._searches[p1]

    ladder_service.cancel_search(p1, "tmm2v2")

    assert "ladder1v1" in ladder_service._searches[p1]
    assert "tmm2v2" not in ladder_service._searches[p1]


async def test_start_search_multiqueue_multiple_players(
    ladder_service: LadderService,
    player_factory,
    queue_factory,
):
    ladder_service.queues["tmm2v2"] = queue_factory("tmm2v2")

    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1000, 10)
    )

    p2 = player_factory(
        "Brackman",
        player_id=2,
        ladder_rating=(1000, 10)
    )

    ladder_service.start_search([p1, p2], "ladder1v1")

    assert "ladder1v1" in ladder_service._searches[p1]
    assert "ladder1v1" in ladder_service._searches[p2]

    ladder_service.start_search([p1, p2], "tmm2v2")

    assert "ladder1v1" in ladder_service._searches[p1]
    assert "tmm2v2" in ladder_service._searches[p1]
    assert "ladder1v1" in ladder_service._searches[p2]
    assert "tmm2v2" in ladder_service._searches[p2]

    ladder_service.cancel_search(p1, "tmm2v2")

    assert "ladder1v1" in ladder_service._searches[p1]
    assert "tmm2v2" not in ladder_service._searches[p1]
    assert "ladder1v1" in ladder_service._searches[p2]
    assert "tmm2v2" not in ladder_service._searches[p2]

    ladder_service.cancel_search(p2, "ladder1v1")

    assert "ladder1v1" not in ladder_service._searches[p1]
    assert "tmm2v2" not in ladder_service._searches[p1]
    assert "ladder1v1" not in ladder_service._searches[p2]
    assert "tmm2v2" not in ladder_service._searches[p2]


async def test_game_start_cancels_search(
    ladder_service: LadderService,
    player_factory,
    queue_factory,
):
    ladder_service.queues["tmm2v2"] = queue_factory("tmm2v2")

    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1000, 10)
    )

    p2 = player_factory(
        "Brackman",
        player_id=2,
        ladder_rating=(1000, 10)
    )
    ladder_service.start_search([p1], "ladder1v1")
    ladder_service.start_search([p2], "ladder1v1")
    ladder_service.start_search([p1], "tmm2v2")
    ladder_service.start_search([p2], "tmm2v2")

    assert "ladder1v1" in ladder_service._searches[p1]
    assert "tmm2v2" in ladder_service._searches[p1]
    assert "ladder1v1" in ladder_service._searches[p2]
    assert "tmm2v2" in ladder_service._searches[p2]

    ladder_service.on_match_found(
        ladder_service._searches[p1]["ladder1v1"],
        ladder_service._searches[p2]["ladder1v1"],
        ladder_service.queues["ladder1v1"]
    )

    assert "ladder1v1" not in ladder_service._searches[p1]
    assert "tmm2v2" not in ladder_service._searches[p1]
    assert "ladder1v1" not in ladder_service._searches[p2]
    assert "tmm2v2" not in ladder_service._searches[p2]


async def test_on_match_found_sets_player_state(
    ladder_service: LadderService,
    player_factory,
):
    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1000, 10)
    )

    p2 = player_factory(
        "Brackman",
        player_id=2,
        ladder_rating=(1000, 10)
    )
    ladder_service.start_search([p1], "ladder1v1")
    ladder_service.start_search([p2], "ladder1v1")

    assert p1.state is PlayerState.SEARCHING_LADDER
    assert p2.state is PlayerState.SEARCHING_LADDER

    ladder_service.on_match_found(
        ladder_service._searches[p1]["ladder1v1"],
        ladder_service._searches[p2]["ladder1v1"],
        ladder_service.queues["ladder1v1"]
    )

    assert p1.state is PlayerState.STARTING_AUTOMATCH
    assert p2.state is PlayerState.STARTING_AUTOMATCH


async def test_start_and_cancel_search(
    ladder_service: LadderService,
    player_factory,
    event_loop,
):
    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1500, 500),
        ladder_games=0
    )

    ladder_service.start_search([p1], "ladder1v1")
    search = ladder_service._searches[p1]["ladder1v1"]
    await exhaust_callbacks(event_loop)

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search in ladder_service.queues["ladder1v1"]._queue
    assert not search.is_cancelled

    ladder_service.cancel_search(p1)

    assert p1.state == PlayerState.IDLE
    assert search.is_cancelled


async def test_start_search_cancels_previous_search(
    ladder_service: LadderService,
    player_factory,
    event_loop,
):
    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1500, 500),
        ladder_games=0
    )

    ladder_service.start_search([p1], "ladder1v1")
    search1 = ladder_service._searches[p1]["ladder1v1"]
    await exhaust_callbacks(event_loop)

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search1 in ladder_service.queues["ladder1v1"]._queue

    ladder_service.start_search([p1], "ladder1v1")
    search2 = ladder_service._searches[p1]["ladder1v1"]
    await exhaust_callbacks(event_loop)

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search1.is_cancelled
    assert search1 not in ladder_service.queues["ladder1v1"]._queue
    assert search2 in ladder_service.queues["ladder1v1"]._queue


async def test_cancel_all_searches(
    ladder_service: LadderService,
    player_factory,
    event_loop,
):
    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1500, 500),
        ladder_games=0
    )

    ladder_service.start_search([p1], "ladder1v1")
    search = ladder_service._searches[p1]["ladder1v1"]
    await exhaust_callbacks(event_loop)

    assert p1.state == PlayerState.SEARCHING_LADDER
    assert search in ladder_service.queues["ladder1v1"]._queue
    assert not search.is_cancelled

    ladder_service.cancel_search(p1)

    assert p1.state == PlayerState.IDLE
    assert search.is_cancelled
    assert "ladder1v1" not in ladder_service._searches[p1]


async def test_cancel_twice(
    ladder_service: LadderService,
    player_factory,
):
    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1500, 500),
        ladder_games=0
    )
    p2 = player_factory(
        "Brackman",
        player_id=2,
        ladder_rating=(2000, 500),
        ladder_games=0
    )

    ladder_service.start_search([p1], "ladder1v1")
    search = ladder_service._searches[p1]["ladder1v1"]
    ladder_service.start_search([p2], "ladder1v1")
    search2 = ladder_service._searches[p2]["ladder1v1"]

    ladder_service.cancel_search(p1)
    assert search.is_cancelled
    assert not search2.is_cancelled

    ladder_service.cancel_search(p1)

    ladder_service.cancel_search(p2)
    assert search2.is_cancelled


@fast_forward(5)
async def test_start_game_called_on_match(
    ladder_service: LadderService,
    player_factory,
):
    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(2300, 64),
        ladder_games=0
    )
    p2 = player_factory(
        "QAI",
        player_id=2,
        ladder_rating=(2350, 125),
        ladder_games=0
    )

    ladder_service.start_game = mock.AsyncMock()
    ladder_service.write_rating_progress = mock.Mock()

    ladder_service.start_search([p1], "ladder1v1")
    ladder_service.start_search([p2], "ladder1v1")
    search1 = ladder_service._searches[p1]["ladder1v1"]

    await search1.await_match()

    ladder_service.write_rating_progress.assert_called()
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


async def test_start_game_map_selection_rating_type(
    ladder_service: LadderService, player_factory
):
    p1 = player_factory(
        ladder_rating=(2000, 50),
        ladder_games=1000,
        global_rating=(1500, 500),
        global_games=0
    )
    p2 = player_factory(
        ladder_rating=(2000, 50),
        ladder_games=1000,
        global_rating=(1500, 500),
        global_games=0
    )

    queue = ladder_service.queues["ladder1v1"]
    queue.rating_type = RatingType.GLOBAL
    queue.map_pools.clear()
    newbie_map_pool = mock.Mock()
    full_map_pool = mock.Mock()
    queue.add_map_pool(newbie_map_pool, None, 500)
    queue.add_map_pool(full_map_pool, 500, None)

    await ladder_service.start_game([p1], [p2], queue)

    newbie_map_pool.choose_map.assert_called_once()
    full_map_pool.choose_map.assert_not_called()


async def test_get_ladder_history(ladder_service: LadderService, players):
    ladder1v1_queue_id = 1
    history = await ladder_service.get_game_history(
        [players.hosting],
        queue_id=ladder1v1_queue_id,
        limit=1
    )

    assert history == [6]


async def test_get_ladder_history_many_maps(ladder_service: LadderService, players):
    ladder1v1_queue_id = 1
    history = await ladder_service.get_game_history(
        [players.hosting],
        queue_id=ladder1v1_queue_id,
        limit=4
    )

    assert history == [6, 5, 4, 3]


async def test_get_ladder_history_1v1(ladder_service: LadderService, player_factory):
    p1 = player_factory("Dostya", player_id=1)
    p2 = player_factory("Rhiza", player_id=2)

    ladder1v1_queue_id = 1
    history = await ladder_service.get_game_history(
        [p1, p2],
        queue_id=ladder1v1_queue_id,
    )

    assert history == [6, 5, 4, 3, 4, 5]


async def test_get_ladder_history_tmm_queue(ladder_service: LadderService, players):
    tmm2v2_queue_id = 2
    history = await ladder_service.get_game_history(
        [players.hosting],
        queue_id=tmm2v2_queue_id,
    )

    assert history == [7, 9, 8]


async def test_get_ladder_history_tmm2v2(ladder_service: LadderService, player_factory):
    p1 = player_factory("Dostya", player_id=1)
    p2 = player_factory("Rhiza", player_id=2)

    tmm2v2_queue_id = 2
    history = await ladder_service.get_game_history(
        [p1, p2],
        queue_id=tmm2v2_queue_id,
    )

    assert history == [7, 9, 8, 7, 6, 5]


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


async def test_write_rating_progress_message(
    ladder_service: LadderService,
    player_factory
):
    player = player_factory(ladder_rating=(1500, 500))
    player.write_message = mock.Mock()

    ladder_service.write_rating_progress(player, RatingType.LADDER_1V1)

    player.write_message.assert_called_once_with({
        "command": "notice",
        "style": "info",
        "text": (
            "<i>Welcome to the matchmaker</i><br><br><b>The "
            "matchmaking system needs to calibrate your skill level; "
            "your first few games may be more imbalanced as the "
            "system attempts to learn your capability as a player."
            "</b><br><b>"
            "Afterwards, you'll be more reliably matched up with "
            "people of your skill level: so don't worry if your "
            "first few games are uneven. This will improve as you "
            "play!</b>"
        )
    })


async def test_write_rating_progress_other_rating(
    ladder_service: LadderService,
    player_factory
):
    player = player_factory(
        ladder_rating=(1500, 500),
        global_rating=(1500, 400.1235)
    )
    player.write_message = mock.Mock()

    # There's no reason we would call it with global, but the logic is the same
    # and global is an available rating that's not ladder
    ladder_service.write_rating_progress(player, RatingType.GLOBAL)

    player.write_message.assert_not_called()


async def test_graceful_shutdown_disables_searching(
    ladder_service: LadderService,
    player_factory
):
    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1000, 10)
    )

    await ladder_service.graceful_shutdown()

    with pytest.raises(DisabledError):
        ladder_service.start_search([p1], "ladder1v1")


async def test_graceful_shutdown_clears_queues(
    ladder_service: LadderService,
    player_factory
):
    p1 = player_factory(
        "Dostya",
        player_id=1,
        ladder_rating=(1000, 10)
    )
    p1.write_message = mock.Mock()

    p2 = player_factory(
        "QAI",
        player_id=2,
        ladder_rating=(2350, 125),
    )
    p2.write_message = mock.Mock()

    p3 = player_factory(
        "Brackman",
        player_id=3,
        ladder_rating=(1000, 10)
    )
    p3.write_message = mock.Mock()

    ladder_service.start_search([p1], "ladder1v1")
    p1.write_message.reset_mock()

    ladder_service.start_search([p2, p3], "tmm2v2")
    p2.write_message.reset_mock()
    p3.write_message.reset_mock()

    await ladder_service.graceful_shutdown()

    p1.write_message.assert_called_once_with({
        "command": "search_info",
        "state": "stop",
        "queue_name": "ladder1v1"
    })
    p2.write_message.assert_called_once_with({
        "command": "search_info",
        "state": "stop",
        "queue_name": "tmm2v2"
    })
    p3.write_message.assert_called_once_with({
        "command": "search_info",
        "state": "stop",
        "queue_name": "tmm2v2"
    })

    assert ladder_service.queues["ladder1v1"]._is_running is False
    assert ladder_service.queues["tmm2v2"]._is_running is False
