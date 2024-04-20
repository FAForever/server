import asyncio
import math
import re
from collections import deque

import pytest
from sqlalchemy import select

from server import config
from server.db.models import (
    game_player_stats,
    matchmaker_queue,
    matchmaker_queue_game
)
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command
from .test_game import (
    client_response,
    idle_response,
    open_fa,
    queue_player_for_matchmaking,
    queue_players_for_matchmaking,
    queue_temp_players_for_matchmaking,
    read_until_launched,
    send_player_options
)


@fast_forward(70)
async def test_game_launch_message(lobby_server):
    _, proto1, _, proto2 = await queue_players_for_matchmaking(lobby_server)

    msg1 = await read_until_command(proto1, "game_launch")
    await open_fa(proto1)
    msg2 = await read_until_command(proto2, "game_launch")

    assert msg2["uid"] == msg1["uid"]
    assert msg2["mod"] == msg1["mod"]
    assert msg2["mapname"] == msg1["mapname"]
    assert msg2["team"] == 3
    assert msg2["faction"] == 1
    assert msg2["expected_players"] == msg1["expected_players"]
    assert msg2["map_position"] == 2

    assert "scmp_015" in msg1["mapname"]
    del msg1["mapname"]
    assert msg1 == {
        "command": "game_launch",
        "args": ["/numgames", 0],
        "uid": 41956,
        "mod": "ladder1v1",
        "name": "ladder1 Vs ladder2",
        "init_mode": 1,
        "game_type": "matchmaker",
        "rating_type": "ladder_1v1",
        "team": 2,
        "faction": 1,
        "expected_players": 2,
        "map_position": 1
    }


@pytest.mark.flaky
@fast_forward(70)
async def test_game_launch_message_map_generator(lobby_server):
    _, proto1, _, proto2 = await queue_players_for_matchmaking(
        lobby_server,
        queue_name="neroxis1v1"
    )

    msg1 = await read_until_command(proto1, "game_launch")
    await open_fa(proto1)
    msg2 = await read_until_command(proto2, "game_launch")

    assert msg1["mapname"] == msg2["mapname"]
    assert re.match(
        "neroxis_map_generator_0.0.0_[0-9a-z]{13}_[0-9a-z]{4}",
        msg1["mapname"]
    )


@fast_forward(70)
async def test_game_launch_message_game_options(lobby_server, tmp_user):
    protos = await queue_temp_players_for_matchmaking(
        lobby_server,
        tmp_user,
        num_players=6,
        queue_name="gameoptions"
    )

    msgs = await asyncio.gather(*[
        client_response(proto) for _, proto in protos
    ])

    for msg in msgs:
        assert msg["game_options"] == {
            "Share": "ShareUntilDeath",
            "UnitCap": 500
        }


@pytest.mark.flaky
@fast_forward(15)
async def test_game_matchmaking_start(lobby_server, database):
    host_id, host, guest_id, guest = await queue_players_for_matchmaking(lobby_server)

    # The player that queued last will be the host
    msg = await read_until_command(host, "game_launch")
    game_id = msg["uid"]
    await open_fa(host)
    await read_until_command(host, "game_info")
    await send_player_options(
        host,
        (host_id, "StartSpot", msg["map_position"]),
        (host_id, "Army", msg["map_position"]),
        (host_id, "Faction", msg["faction"]),
        (host_id, "Color", msg["map_position"]),
    )
    await read_until_command(host, "game_info")

    await read_until_command(guest, "game_launch")
    await open_fa(guest)
    await read_until_command(host, "game_info")
    await read_until_command(guest, "game_info")
    await send_player_options(
        host,
        (guest_id, "StartSpot", msg["map_position"]),
        (guest_id, "Army", msg["map_position"]),
        (guest_id, "Faction", msg["faction"]),
        (guest_id, "Color", msg["map_position"]),
    )
    await asyncio.sleep(0.5)

    await host.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Launching"]
    })

    # Wait for db to be updated
    await read_until_launched(host, game_id)
    await read_until_launched(guest, game_id)

    async with database.acquire() as conn:
        result = await conn.execute(select(
            game_player_stats.c.faction,
            game_player_stats.c.color,
            game_player_stats.c.team,
            game_player_stats.c.place,
        ).where(game_player_stats.c.gameId == game_id))
        rows = result.fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row.faction == 1
            assert row.color in (1, 2)
            assert row.team is not None
            assert row.place is not None

        result = await conn.execute(select(
            matchmaker_queue.c.technical_name,
        ).select_from(
            matchmaker_queue_game.outerjoin(matchmaker_queue)
        ).where(matchmaker_queue_game.c.game_stats_id == game_id))
        row = result.fetchone()
        assert row.technical_name == "ladder1v1"


@fast_forward(15)
async def test_game_matchmaking_start_while_matched(lobby_server):
    _, proto1, _, _ = await queue_players_for_matchmaking(lobby_server)

    # Trying to queue again after match was found should generate an error
    await proto1.send_message({
        "command": "game_matchmaking",
        "state": "start",
    })

    msg = await read_until_command(proto1, "notice", style="error", timeout=5)
    assert msg["text"].startswith("Can't join a queue while ladder1 is in")


@fast_forward(120)
async def test_game_matchmaking_timeout(lobby_server, game_service):
    _, proto1, _, proto2 = await queue_players_for_matchmaking(lobby_server)

    msg1, msg2 = await asyncio.gather(
        idle_response(proto1, timeout=120),
        idle_response(proto2, timeout=120)
    )
    # LEGACY BEHAVIOUR: The host does not respond with the appropriate GameState
    # so the match is cancelled. However, the client does not know how to
    # handle `match_cancelled` messages so we still send `game_launch` to
    # prevent the client from showing that it is searching when it really isn't.
    await read_until_command(proto2, "match_cancelled", timeout=120)
    await read_until_command(proto1, "match_cancelled", timeout=120)

    assert msg1["uid"] == msg2["uid"]
    assert msg1["mod"] == "ladder1v1"
    assert msg2["mod"] == "ladder1v1"

    # Ensure that the game is cleaned up
    await read_until_command(
        proto1,
        "game_info",
        state="closed",
        timeout=15
    )
    assert game_service._games == {}

    # Player's state is reset once they leave the game
    await proto1.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })
    await proto1.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef"
    })
    await read_until_command(proto1, "search_info", state="start", timeout=5)

    # And not before they've left the game
    await proto2.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef"
    })
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(proto2, "search_info", state="start", timeout=5)


@fast_forward(120)
async def test_game_matchmaking_timeout_guest(lobby_server, game_service):
    _, proto1, _, proto2 = await queue_players_for_matchmaking(lobby_server)

    msg1, msg2 = await asyncio.gather(
        client_response(proto1),
        client_response(proto2)
    )
    # GameState Launching is never sent
    await read_until_command(proto2, "match_cancelled", timeout=120)
    await read_until_command(proto1, "match_cancelled", timeout=120)

    assert msg1["uid"] == msg2["uid"]
    assert msg1["mod"] == "ladder1v1"
    assert msg2["mod"] == "ladder1v1"

    # Ensure that the game is cleaned up
    await read_until_command(
        proto1,
        "game_info",
        state="closed",
        timeout=5
    )
    assert game_service._games == {}

    # Player's state is reset once they leave the game
    await proto1.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })
    await proto1.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef"
    })
    await read_until_command(proto1, "search_info", state="start", timeout=5)

    # And not before they've left the game
    await proto2.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef"
    })
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(proto2, "search_info", state="start", timeout=5)


@fast_forward(15)
async def test_game_matchmaking_cancel(lobby_server):
    _, proto = await queue_player_for_matchmaking(
        ("ladder1", "ladder1"),
        lobby_server,
        queue_name="ladder1v1"
    )

    await proto.send_message({
        "command": "game_matchmaking",
        "state": "stop",
    })

    # The server should respond with a matchmaking stop message
    msg = await read_until_command(proto, "search_info")

    assert msg == {
        "command": "search_info",
        "queue_name": "ladder1v1",
        "state": "stop",
    }

    # Extra message even though the player is not in a queue
    await proto.send_message({
        "command": "game_matchmaking",
        "queue_name": "ladder1v1",
        "state": "stop"
    })
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(proto, "search_info", timeout=5)


@fast_forward(50)
async def test_game_matchmaking_disconnect(lobby_server):
    _, proto1, _, proto2 = await queue_players_for_matchmaking(lobby_server)
    # One player disconnects before the game has launched
    await proto1.close()

    msg = await read_until_command(proto2, "match_cancelled", timeout=120)

    assert msg == {"command": "match_cancelled", "game_id": 41956}


@pytest.mark.flaky
@fast_forward(130)
async def test_game_matchmaking_close_fa_and_requeue(lobby_server):
    _, proto1, _, proto2 = await queue_players_for_matchmaking(lobby_server)

    _, _ = await asyncio.gather(
        client_response(proto1),
        client_response(proto2)
    )
    # Players can't connect to eachother, so one of them abandons the game and
    # joins the queue again
    await proto1.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })
    await proto1.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue": "ladder1v1"
    })
    await read_until_command(proto1, "search_info", state="start", timeout=5)

    # The other player waits for the game to time out and then queues again
    await read_until_command(proto2, "match_cancelled", timeout=120)
    await proto2.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })
    await proto2.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue": "ladder1v1"
    })

    await read_until_command(proto1, "match_found", timeout=5)


@pytest.mark.flaky
@fast_forward(200)
async def test_anti_map_repetition(lobby_server):
    played_maps: deque[str] = deque(maxlen=config.LADDER_ANTI_REPETITION_LIMIT)

    # Play a bunch of games and make sure we never get the same map in our
    # recent history. Games end in a draw so that players keep matching.
    for _ in range(20):
        ret = await queue_players_for_matchmaking(lobby_server)
        player1_id, proto1, player2_id, proto2 = ret
        msg1, msg2 = await asyncio.gather(
            client_response(proto1),
            client_response(proto2)
        )
        mapname = msg1["mapname"]
        game_id = msg1["uid"]
        assert mapname not in played_maps
        played_maps.append(mapname)

        for player_id, msg in ((player1_id, msg1), (player2_id, msg2)):
            await send_player_options(
                proto1,
                (player_id, "StartSpot", msg["map_position"]),
                (player_id, "Army", msg["map_position"]),
                (player_id, "Faction", msg["faction"]),
                (player_id, "Color", msg["map_position"]),
            )

        for proto in (proto1, proto2):
            await proto.send_message({
                "command": "GameState",
                "target": "game",
                "args": ["Launching"]
            })

        for proto in (proto1, proto2):
            await read_until_launched(proto, game_id)

        for proto in (proto1, proto2):
            for result in (
                [1, "draw 0"],
                [2, "draw 0"],
            ):
                await proto.send_message({
                    "command": "GameResult",
                    "target": "game",
                    "args": result
                })

        for proto in (proto1, proto2):
            await proto.send_message({
                "command": "GameEnded",
                "target": "game",
                "args": []
            })

        await asyncio.gather(
            proto1.close(),
            proto2.close()
        )


@fast_forward(10)
async def test_matchmaker_info_message(lobby_server, mocker):
    mocker.patch("server.matchmaker.pop_timer.time", return_value=1_562_000_000)
    mocker.patch(
        "server.matchmaker.matchmaker_queue.time.time",
        return_value=1_562_000_000,
    )

    _, _, proto = await connect_and_sign_in(
        ("ladder1", "ladder1"),
        lobby_server
    )
    # Because the mocking hasn"t taken effect on the first message we need to
    # wait for the second message
    msg = await read_until_command(proto, "matchmaker_info")
    msg = await read_until_command(proto, "matchmaker_info")

    assert "queues" in msg
    for queue in msg["queues"]:
        assert "queue_name" in queue
        assert "team_size" in queue
        assert "num_players" in queue

        assert queue["queue_pop_time"] == "2019-07-01T16:53:21+00:00"
        assert queue["queue_pop_time_delta"] == math.ceil(
            config.QUEUE_POP_TIME_MAX / 2
        )
        assert queue["boundary_80s"] == []
        assert queue["boundary_75s"] == []


@fast_forward(10)
async def test_command_matchmaker_info(lobby_server, mocker):
    mocker.patch("server.matchmaker.pop_timer.time", return_value=1_562_000_000)
    mocker.patch(
        "server.matchmaker.matchmaker_queue.time.time",
        return_value=1_562_000_000,
    )

    _, _, proto = await connect_and_sign_in(
        ("ladder1", "ladder1"),
        lobby_server
    )

    await read_until_command(proto, "game_info")
    # Wait for the dirty reporting to happen
    await read_until_command(proto, "matchmaker_info")

    await proto.send_message({"command": "matchmaker_info"})
    msg = await read_until_command(proto, "matchmaker_info")
    assert "queues" in msg
    assert len(msg["queues"]) == 4
    for queue in msg["queues"]:
        assert "queue_name" in queue
        assert "team_size" in queue
        assert "num_players" in queue

        assert queue["queue_pop_time"] == "2019-07-01T16:53:21+00:00"
        assert queue["queue_pop_time_delta"] == math.ceil(
            config.QUEUE_POP_TIME_MAX / 2
        )
        assert queue["boundary_80s"] == []
        assert queue["boundary_75s"] == []


@fast_forward(10)
async def test_matchmaker_info_message_on_cancel(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ("ladder1", "ladder1"),
        lobby_server
    )

    await read_until_command(proto, "game_info")
    await read_until_command(proto, "matchmaker_info")

    await proto.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef"
    })

    async def read_update_msg():
        while True:
            # Update message because a new player joined the queue
            msg = await read_until_command(proto, "matchmaker_info")

            queue_message = next(
                q for q in msg["queues"] if q["queue_name"] == "ladder1v1"
            )
            if not queue_message["boundary_80s"]:
                continue

            assert len(queue_message["boundary_80s"]) == 1

            return

    await asyncio.wait_for(read_update_msg(), 2)

    await proto.send_message({
        "command": "game_matchmaking",
        "state": "stop",
    })

    # Update message because we left the queue
    msg = await read_until_command(proto, "matchmaker_info")

    queue_message = next(q for q in msg["queues"] if q["queue_name"] == "ladder1v1")
    assert len(queue_message["boundary_80s"]) == 0


@fast_forward(10)
async def test_search_info_messages(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ("ladder1", "ladder1"),
        lobby_server
    )
    await read_until_command(proto, "game_info")

    # Start searching
    await proto.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef"
    })
    msg = await read_until_command(proto, "search_info")
    assert msg == {
        "command": "search_info",
        "queue_name": "ladder1v1",
        "state": "start"
    }
    # TODO: Join a second queue here

    # Stop searching
    await proto.send_message({
        "command": "game_matchmaking",
        "state": "stop",
    })
    msg = await read_until_command(proto, "search_info")
    assert msg == {
        "command": "search_info",
        "queue_name": "ladder1v1",
        "state": "stop"
    }

    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(proto, "search_info", timeout=5)
