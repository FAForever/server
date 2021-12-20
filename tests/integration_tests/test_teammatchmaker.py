import asyncio

import pytest
from sqlalchemy import and_, select

from server.db.models import (
    game_player_stats,
    leaderboard,
    leaderboard_rating,
    leaderboard_rating_journal
)
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until, read_until_command
from .test_game import client_response, get_player_ratings, send_player_options

pytestmark = pytest.mark.asyncio


async def connect_players(lobby_server):
    res = await asyncio.gather(*[
        connect_and_sign_in(
            (f"ladder{i+1}",) * 2,
            lobby_server
        )
        for i in range(4)
    ])
    protos = [proto for _, _, proto in res]
    ids = [id_ for id_, _, _ in res]

    return protos, ids


async def queue_players_for_matchmaking(lobby_server):
    protos, ids = await connect_players(lobby_server)

    await asyncio.gather(*[
        read_until_command(proto, "game_info") for proto in protos
    ])

    await asyncio.gather(*[
        proto.send_message({
            "command": "set_party_factions",
            "factions": ["uef"]
        })
        for proto in protos
    ])
    await asyncio.gather(*[
        proto.send_message({
            "command": "game_matchmaking",
            "state": "start",
            "queue_name": "tmm2v2"
        })
        for proto in protos
    ])

    # If the players did not match, this will fail due to a timeout error
    await asyncio.gather(*[
        read_until_command(proto, "match_found", timeout=30) for proto in protos
    ])

    return protos, ids


async def matchmaking_client_response(proto):
    await read_until_command(proto, "match_found", timeout=30)
    return await client_response(proto)


@fast_forward(10)
async def test_info_message(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ("ladder1", "ladder1"), lobby_server
    )

    await read_until_command(proto, "game_info")

    await proto.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef",
        "queue_name": "tmm2v2"
    })

    msg = await read_until_command(proto, "matchmaker_info")

    assert msg["queues"]
    for queue in msg["queues"]:
        num_players = queue["num_players"]

        if queue["queue_name"] == "tmm2v2":
            assert num_players == 1
        else:
            assert num_players == 0


@fast_forward(10)
async def test_game_matchmaking(lobby_server):
    protos, _ = await queue_players_for_matchmaking(lobby_server)

    msgs = await asyncio.gather(*[client_response(proto) for proto in protos])

    uid = set(msg["uid"] for msg in msgs)
    assert len(uid) == 1
    for msg in msgs:
        assert msg["game_type"] == "matchmaker"
        assert "None" not in msg["name"]
        assert msg["mod"] == "faf"
        assert msg["expected_players"] == 4
        assert msg["team"] in (2, 3)
        assert msg["map_position"] in (1, 2, 3, 4)
        assert msg["faction"] == 1


@fast_forward(15)
async def test_game_matchmaking_multiqueue(lobby_server):
    protos, _ = await connect_players(lobby_server)

    await asyncio.gather(*[
        read_until_command(proto, "game_info") for proto in protos
    ])

    await protos[0].send_message({
        "command": "set_party_factions",
        "factions": ["uef"]
    })
    await protos[0].send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": "ladder1v1"
    })
    await read_until_command(protos[0], "search_info", state="start")
    await asyncio.gather(*[
        proto.send_message({
            "command": "set_party_factions",
            "factions": ["aeon"]
        })
        for proto in protos
    ])
    await asyncio.gather(*[
        proto.send_message({
            "command": "game_matchmaking",
            "state": "start",
            "queue_name": "tmm2v2"
        })
        for proto in protos
    ])
    msg = await read_until_command(
        protos[0],
        "search_info",
        queue_name="ladder1v1"
    )
    assert msg["state"] == "stop"

    msgs = await asyncio.gather(*[client_response(proto) for proto in protos])

    uid = set(msg["uid"] for msg in msgs)
    assert len(uid) == 1
    for msg in msgs:
        assert msg["game_type"] == "matchmaker"
        assert "None" not in msg["name"]
        assert msg["mod"] == "faf"
        assert msg["expected_players"] == 4
        assert msg["team"] in (2, 3)
        assert msg["map_position"] in (1, 2, 3, 4)
        assert msg["faction"] == 2


@fast_forward(10)
async def test_game_matchmaking_with_parties(lobby_server):
    protos, ids = await connect_players(lobby_server)
    id1, id2, id3, id4 = ids
    proto1, proto2, proto3, proto4 = protos

    # Setup parties
    await proto1.send_message({
        "command": "invite_to_party",
        "recipient_id": id2
    })
    await proto3.send_message({
        "command": "invite_to_party",
        "recipient_id": id4
    })
    await read_until_command(proto2, "party_invite")
    await proto2.send_message({
        "command": "accept_party_invite",
        "sender_id": id1
    })
    await read_until_command(proto4, "party_invite")
    await proto4.send_message({
        "command": "accept_party_invite",
        "sender_id": id3
    })
    await read_until_command(proto1, "update_party")
    await read_until_command(proto3, "update_party")

    await proto1.send_message({
        "command": "set_party_factions",
        "factions": ["seraphim"]
    })
    await proto2.send_message({
        "command": "set_party_factions",
        "factions": ["aeon"]
    })
    await proto3.send_message({
        "command": "set_party_factions",
        "factions": ["cybran"]
    })
    await proto4.send_message({
        "command": "set_party_factions",
        "factions": ["seraphim"]
    })
    await read_until_command(proto1, "update_party")
    await read_until_command(proto3, "update_party")

    # Queue both parties
    await proto1.send_message({
        "command": "game_matchmaking",
        "queue_name": "tmm2v2",
        "state": "start",
    })
    # Change faction selection after queueing
    await proto1.send_message({
        "command": "set_party_factions",
        "factions": ["uef"]
    })
    await proto3.send_message({
        "command": "game_matchmaking",
        "queue_name": "tmm2v2",
        "state": "start",
    })

    msgs = await asyncio.gather(*[
        matchmaking_client_response(proto) for proto in protos
    ])

    uid = set(msg["uid"] for msg in msgs)
    assert len(uid) == 1
    for i, msg in enumerate(msgs):
        assert msg["game_type"] == "matchmaker"
        assert "None" not in msg["name"]
        assert msg["mod"] == "faf"
        assert msg["expected_players"] == 4
        assert msg["team"] in (2, 3)
        assert msg["map_position"] in (1, 2, 3, 4)
        assert msg["faction"] == i + 1


@fast_forward(30)
async def test_newbie_matchmaking_with_parties(lobby_server):
    # Two completely new tmm players
    id1, _, proto1 = await connect_and_sign_in(
        ("ladder1", "ladder1"), lobby_server
    )
    id2, _, proto2 = await connect_and_sign_in(
        ("ladder2", "ladder2"), lobby_server
    )
    # Two more experienced players
    _, _, proto3 = await connect_and_sign_in(
        ("tmm1", "tmm1"), lobby_server
    )
    _, _, proto4 = await connect_and_sign_in(
        ("tmm2", "tmm2"), lobby_server
    )
    protos = (proto1, proto2, proto3, proto4)

    await asyncio.gather(*[
        read_until_command(proto, "game_info") for proto in protos
    ])

    # Setup new players in a party
    await proto1.send_message({
        "command": "invite_to_party",
        "recipient_id": id2
    })
    await read_until_command(proto2, "party_invite")
    await proto2.send_message({
        "command": "accept_party_invite",
        "sender_id": id1
    })
    await read_until_command(proto1, "update_party")

    # Queue all players
    await proto1.send_message({
        "command": "game_matchmaking",
        "queue_name": "tmm2v2",
        "state": "start",
    })
    # The tmm players are queuing solo
    await proto3.send_message({
        "command": "game_matchmaking",
        "queue_name": "tmm2v2",
        "state": "start",
    })
    await proto4.send_message({
        "command": "game_matchmaking",
        "queue_name": "tmm2v2",
        "state": "start",
    })

    msgs = await asyncio.gather(*[
        matchmaking_client_response(proto) for proto in protos
    ])

    uid = set(msg["uid"] for msg in msgs)
    assert len(uid) == 1
    for msg in msgs:
        assert msg["game_type"] == "matchmaker"
        assert "None" not in msg["name"]
        assert msg["mod"] == "faf"
        assert msg["expected_players"] == 4
        assert msg["team"] in (2, 3)
        assert msg["map_position"] in (1, 2, 3, 4)


@fast_forward(120)
async def test_game_matchmaking_multiqueue_timeout(lobby_server):
    protos, _ = await connect_players(lobby_server)

    await asyncio.gather(*[
        read_until_command(proto, "game_info") for proto in protos
    ])

    await protos[0].send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": "ladder1v1"
    })
    await read_until_command(protos[0], "search_info", state="start")
    await asyncio.gather(*[
        proto.send_message({
            "command": "game_matchmaking",
            "state": "start",
            "queue_name": "tmm2v2"
        })
        for proto in protos
    ])
    await read_until_command(protos[1], "search_info", state="start")
    msg = await read_until_command(
        protos[0],
        "search_info",
        queue_name="ladder1v1"
    )
    assert msg["state"] == "stop"

    # Don't send any GPGNet messages so the match times out
    await read_until_command(protos[0], "match_cancelled", timeout=120)

    # Player's state is not reset immediately
    await protos[0].send_message({
        "command": "game_matchmaking",
        "state": "start",
    })
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(protos[1], "search_info", state="start", timeout=5)

    # Player's state is reset once they leave the game
    await protos[0].send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })
    await protos[0].send_message({
        "command": "game_matchmaking",
        "state": "start",
    })
    await read_until_command(
        protos[0],
        "search_info",
        state="start",
        queue_name="ladder1v1",
        timeout=5
    )


@fast_forward(60)
async def test_game_matchmaking_multiqueue_multimatch(lobby_server):
    """
    Scenario where both queues could possibly generate a match.
    Queues:
        ladder1v1 - 2 players join
        tmm2v2    - 4 players join
    Result:
        Either one of the queues generates a match, but not both.
    """
    protos, _ = await connect_players(lobby_server)

    await asyncio.gather(*[
        read_until_command(proto, "game_info") for proto in protos
    ])

    ladder1v1_tasks = [
        proto.send_message({
            "command": "game_matchmaking",
            "state": "start",
            "queue_name": "ladder1v1"
        })
        for proto in protos[:2]
    ]
    await asyncio.gather(*[
        proto.send_message({
            "command": "game_matchmaking",
            "state": "start",
            "queue_name": "tmm2v2"
        })
        for proto in protos
    ] + ladder1v1_tasks)
    msg1 = await read_until_command(protos[0], "match_found")
    msg2 = await read_until_command(protos[1], "match_found")

    matched_queue = msg1["queue_name"]
    if matched_queue == "ladder1v1":
        with pytest.raises(asyncio.TimeoutError):
            await read_until_command(protos[2], "match_found", timeout=3)
        with pytest.raises(asyncio.TimeoutError):
            await read_until_command(protos[3], "match_found", timeout=3)
        with pytest.raises(asyncio.TimeoutError):
            await read_until_command(protos[2], "search_info", timeout=3)
        with pytest.raises(asyncio.TimeoutError):
            await read_until_command(protos[3], "search_info", timeout=3)
    else:
        await read_until_command(protos[2], "match_found", timeout=3)
        await read_until_command(protos[3], "match_found", timeout=3)

    assert msg1 == msg2

    def other_cancelled(msg):
        return (
            msg["command"] == "search_info"
            and msg["queue_name"] != matched_queue
        )
    msg1 = await read_until(protos[0], other_cancelled, timeout=3)
    msg2 = await read_until(protos[1], other_cancelled, timeout=3)
    assert msg1 == msg2
    assert msg1["state"] == "stop"


@fast_forward(120)
async def test_game_matchmaking_timeout(lobby_server):
    protos, _ = await queue_players_for_matchmaking(lobby_server)

    # We don't send the `GameState: Lobby` command so the game should time out
    await asyncio.gather(*[
        read_until_command(proto, "match_cancelled", timeout=120)
        for proto in protos
    ])

    # Player's state is reset once they leave the game
    await protos[0].send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })
    await protos[0].send_message({
        "command": "game_matchmaking",
        "state": "start",
    })
    await read_until_command(
        protos[0],
        "search_info",
        state="start",
        queue_name="ladder1v1",
        timeout=5
    )


@fast_forward(120)
async def test_game_ratings(lobby_server):
    protos, ids = await queue_players_for_matchmaking(lobby_server)

    msgs = await asyncio.gather(*[client_response(proto) for proto in protos])
    # Configure. Just send options for all players so we don't need to worry
    # about who is the host.
    for proto in protos:
        for player_id, msg in zip(ids, msgs):
            slot = msg["map_position"]
            await send_player_options(
                proto,
                [player_id, "Army", slot],
                [player_id, "Color", slot],
                [player_id, "Faction", msg["faction"]],
                [player_id, "StartSpot", slot],
                [player_id, "Team", msg["team"]],
            )
    # Launch
    await asyncio.gather(*[proto.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Launching"]
    }) for proto in protos])

    await asyncio.gather(*[read_until(
        proto,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    ) for proto in protos])

    # Report results
    for proto in protos:
        for result in (
            [1, "victory 10"],
            [2, "defeat -10"],
            [3, "victory 10"],
            [4, "defeat -10"]
        ):
            await proto.send_message({
                "target": "game",
                "command": "GameResult",
                "args": result
            })
    for proto in protos:
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })

    new_ratings = await get_player_ratings(
        protos[0],
        *[f"ladder{i}" for i in range(1, 5)],
        rating_type="tmm_2v2"
    )
    for _, rating in new_ratings.items():
        assert rating != (1500, 500)


@fast_forward(60)
async def test_ratings_initialized_based_on_global(lobby_server):
    test_id, _, proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )

    msg = await read_until_command(proto, "player_info")
    assert msg == {
        "command": "player_info",
        "players": [
            {
                "id": 1,
                "login": "test",
                "clan": "678",
                "country": "",
                "ratings": {
                    "global": {
                        "rating": [2000.0, 125.0],
                        "number_of_games": 5
                    },
                    "ladder_1v1": {
                        "rating": [2000.0, 125.0],
                        "number_of_games": 5
                    }
                },
                "global_rating": [2000.0, 125.0],
                "ladder_rating": [2000.0, 125.0],
                "number_of_games": 5,
            }
        ]
    }

    await proto.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef",
        "queue_name": "tmm2v2"
    })

    # Need to connect another user to guarantee triggering a message containing
    # the updated player info
    _, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )

    msg = await read_until_command(proto2, "player_info")
    player = list(filter(lambda p: p["id"] == test_id, msg["players"]))[0]
    assert player == {
        "id": 1,
        "login": "test",
        "clan": "678",
        "country": "",
        "ratings": {
            "global": {
                "rating": [2000.0, 125.0],
                "number_of_games": 5
            },
            "ladder_1v1": {
                "rating": [2000.0, 125.0],
                "number_of_games": 5
            },
            "tmm_2v2": {
                "rating": [2000.0, 250.0],
                "number_of_games": 0
            }
        },
        "global_rating": [2000.0, 125.0],
        "ladder_rating": [2000.0, 125.0],
        "number_of_games": 5,
    }


@fast_forward(60)
async def test_ratings_initialized_based_on_global_persisted(
    lobby_server,
    database
):
    # 2 ladder and global noobs
    _, _, proto1 = await connect_and_sign_in(
        ("ladder1", "ladder1"), lobby_server
    )
    _, _, proto2 = await connect_and_sign_in(
        ("ladder2", "ladder2"), lobby_server
    )
    # One global pro with no tmm games
    test_id, _, proto3 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    # One tmm pro to balance the match
    _, _, proto4 = await connect_and_sign_in(
        ("tmm2", "tmm2"), lobby_server
    )
    protos = [proto1, proto2, proto3, proto4]
    for proto in protos:
        # Read the initial game list
        await read_until_command(proto, "player_info")
        # Read the broadcasted update
        await read_until_command(proto, "player_info")

    for proto in protos:
        await proto.send_message({
            "command": "game_matchmaking",
            "state": "start",
            "queue_name": "tmm2v2"
        })
        await read_until_command(proto, "search_info")

    msg1, msg2, msg3, msg4 = await asyncio.gather(*[
        matchmaking_client_response(proto) for proto in protos
    ])
    # So it doesn't matter who is host
    await asyncio.gather(*[
        proto.send_message({
            "command": "GameState",
            "target": "game",
            "args": ["Launching"]
        }) for proto in protos
    ])

    army1 = msg1["map_position"]
    army2 = msg2["map_position"]
    test_army = msg3["map_position"]
    army4 = msg4["map_position"]

    for result in (
        [army1, "defeat -10"],
        [army2, "defeat -10"],
        [army4, "defeat -10"],
        [test_army, "victory 10"],
    ):
        for proto in protos:
            await proto.send_message({
                "target": "game",
                "command": "GameResult",
                "args": result
            })

    for proto in protos:
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })

    await read_until(
        proto3,
        lambda msg: msg["command"] == "player_info"
        and any(player["id"] == test_id for player in msg["players"]),
        timeout=15
    )

    async with database.acquire() as conn:
        result = await conn.execute(
            select([leaderboard_rating]).select_from(
                leaderboard.join(leaderboard_rating)
            ).where(and_(
                leaderboard.c.technical_name == "tmm_2v2",
                leaderboard_rating.c.login_id == test_id
            ))
        )
        row = result.fetchone()
        assert row.mean > 2000

        result = await conn.execute(
            select([leaderboard_rating_journal]).select_from(
                leaderboard
                .join(leaderboard_rating_journal)
                .join(game_player_stats)
            ).where(and_(
                leaderboard.c.technical_name == "tmm_2v2",
                game_player_stats.c.playerId == test_id
            ))
        )
        rows = result.fetchall()
        assert len(rows) == 1
        assert rows[0].rating_mean_before == 2000
        assert rows[0].rating_deviation_before == 250


@fast_forward(30)
async def test_party_cleanup_on_abort(lobby_server):
    for _ in range(3):
        _, _, proto = await connect_and_sign_in(
            ("test", "test_password"), lobby_server
        )
        await read_until_command(proto, "game_info")

        await proto.send_message({
            "command": "game_matchmaking",
            "state": "start",
            "queue_name": "tmm2v2"
        })
        # The queue was successful. This would time out on failure.
        await read_until_command(proto, "search_info", state="start")

        # Trigger an abort
        await proto.send_message({"some": "garbage"})

        # Loop to reconnect
