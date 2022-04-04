import asyncio
import gc
import json
import time
from collections import defaultdict
from datetime import datetime

import pytest
from sqlalchemy import select

from server.db.models import game_player_stats
from server.games.game_results import GameOutcome
from server.protocol import Protocol
from server.timing import datetime_now
from tests.utils import fast_forward

from .conftest import (
    connect_and_sign_in,
    connect_mq_consumer,
    read_until,
    read_until_command
)


async def host_game(
    proto: Protocol,
    *,
    mod: str = "faf",
    visibility: str = "public",
    **kwargs
) -> int:
    await proto.send_message({
        "command": "game_host",
        "mod": mod,
        "visibility": visibility,
        **kwargs
    })
    msg = await read_until_command(proto, "game_launch")
    game_id = int(msg["uid"])

    await open_fa(proto)
    await read_until_command(proto, "HostGame", target="game")

    return game_id


async def join_game(proto: Protocol, uid: int):
    await proto.send_message({
        "command": "game_join",
        "uid": uid
    })
    await read_until_command(proto, "game_launch", timeout=10)
    await open_fa(proto)
    # HACK: Yield long enough for the server to process our message
    await asyncio.sleep(0.5)


async def setup_game_1v1(
    host_proto: Protocol,
    host_id: int,
    guest_proto: Protocol,
    guest_id: int,
    mod: str = "faf"
):
    # Set up the game
    game_id = await host_game(host_proto, mod=mod)
    await join_game(guest_proto, game_id)
    # Set player options
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "Team", 1],
        [host_id, "StartSpot", 1],
        [host_id, "Faction", 1],
        [host_id, "Color", 1],
        [guest_id, "Army", 2],
        [guest_id, "Team", 2],
        [guest_id, "StartSpot", 2],
        [guest_id, "Faction", 2],
        [guest_id, "Color", 2],
    )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    await read_until_launched(host_proto, game_id)

    return game_id


async def read_until_launched(proto: Protocol, uid=None, timeout=60):
    def predecate(cmd) -> bool:
        if cmd["command"] != "game_info":
            return False

        if uid is not None and cmd["uid"] != uid:
            return False

        return cmd["launched_at"] is not None

    return await read_until(proto, predecate, timeout=timeout)


async def client_response(proto, timeout=10):
    msg = await read_until_command(proto, "game_launch", timeout=timeout)
    await open_fa(proto)
    return msg


async def idle_response(proto, timeout=10):
    msg = await read_until_command(proto, "game_launch", timeout=timeout)
    await proto.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Idle"]
    })
    return msg


async def open_fa(proto):
    """Simulate FA opening"""

    await proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Idle"]
    })
    await proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Lobby"]
    })


async def start_search(proto, queue_name="ladder1v1"):
    await proto.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef",
        "queue_name": queue_name
    })
    return await read_until_command(
        proto,
        "search_info",
        state="start",
        queue_name=queue_name,
        timeout=10
    )


async def queue_player_for_matchmaking(user, lobby_server, queue_name="ladder1v1"):
    player_id, _, proto = await connect_and_sign_in(user, lobby_server)
    await read_until_command(proto, "game_info")
    await start_search(proto, queue_name)

    return player_id, proto


async def queue_players_for_matchmaking(lobby_server, queue_name: str = "ladder1v1"):
    player1_id, proto1 = await queue_player_for_matchmaking(
        ("ladder1", "ladder1"),
        lobby_server,
        queue_name
    )
    player2_id, _, proto2 = await connect_and_sign_in(
        ("ladder2", "ladder2"),
        lobby_server
    )

    await read_until_command(proto2, "game_info")

    await proto2.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": 1,  # Python client sends factions as numbers
        "queue_name": queue_name
    })
    await read_until_command(proto2, "search_info", state="start")

    # If the players did not match, this will fail due to a timeout error
    await read_until_command(proto1, "match_found", timeout=30)
    await read_until_command(proto2, "match_found")

    return player1_id, proto1, player2_id, proto2


async def queue_temp_players_for_matchmaking(
    lobby_server,
    tmp_user,
    num_players,
    queue_name,
):
    """
    Queue an arbitrary number of players for matchmaking in a particular queue
    by setting up temp users.
    """
    users = await asyncio.gather(*[
        tmp_user(queue_name)
        for _ in range(num_players)
    ])
    protos = await asyncio.gather(*[
        queue_player_for_matchmaking(user, lobby_server, queue_name)
        for user in users
    ])

    # If the players did not match, this will fail due to a timeout error
    await asyncio.gather(*[
        read_until_command(proto, "match_found", timeout=30)
        for _, proto in protos
    ])

    return protos


async def get_player_ratings(proto, *names, rating_type="global"):
    """
    Wait for `player_info` messages until all player names have been found.
    Then return a dictionary containing all those players ratings
    """
    ratings = {}
    while set(ratings.keys()) != set(names):
        msg = await read_until_command(proto, "player_info")
        ratings.update({
            player_info["login"]: player_info["ratings"][rating_type]["rating"]
            for player_info in msg["players"]
        })
    return ratings


async def get_player_ratings_all(proto, *names, old_ratings={}):
    """
    Like `get_player_ratings` but find all rating types instead of just one and
    return a nested dictionary containing all those ratings.

    If old_ratings is passed, wait for ratings to be different from old_ratings.
    """
    def _nested_keys(nested_dict):
        return set(k + r for k, v in nested_dict.items() for r in v.keys())

    ratings = defaultdict(dict)
    target_keys = _nested_keys(old_ratings)
    while _nested_keys(ratings) != target_keys:
        msg = await read_until_command(proto, "player_info")
        for player_info in msg["players"]:
            for rating_type, rating in player_info["ratings"].items():
                login = player_info["login"]
                player_rating = tuple(rating["rating"])
                if player_rating != old_ratings.get(login, {}).get(rating_type):
                    ratings[login][rating_type] = player_rating

    return dict(ratings)


async def send_player_options(proto, *options):
    for option in options:
        await proto.send_message({
            "target": "game",
            "command": "PlayerOption",
            "args": list(option)
        })


@fast_forward(20)
async def test_game_validity_states(lobby_server):
    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    # Set up the game
    game_id = await host_game(host_proto)
    msg = await read_until_command(host_proto, "game_info", uid=game_id, timeout=5)
    assert msg["validity"] == ["single_player"]

    # The host configures themselves, causing them to show up as connected
    await send_player_options(host_proto, [host_id, "Team", 1])
    msg = await read_until_command(host_proto, "game_info", uid=game_id, timeout=5)
    assert msg["validity"] == ["uneven_teams_not_ranked", "single_player"]

    # Change the map to an unranked map
    await host_proto.send_message({
        "target": "game",
        "command": "GameOption",
        "args": [
            "ScenarioFile",
            "/maps/neroxis_map_generator_sneaky_map/sneaky_map_scenario.lua"
        ]
    })
    msg = await read_until_command(host_proto, "game_info", uid=game_id, timeout=5)
    assert msg["validity"] == [
        "bad_map",
        "uneven_teams_not_ranked",
        "single_player"
    ]

    # Another player joins
    await join_game(guest_proto, game_id)
    await send_player_options(host_proto, [guest_id, "Team", 1])
    msg = await read_until_command(host_proto, "game_info", uid=game_id, timeout=5)
    assert msg["validity"] == ["bad_map"]

    # Change the map to a ranked map
    await host_proto.send_message({
        "target": "game",
        "command": "GameOption",
        "args": ["ScenarioFile", "/maps/scmp_001/scmp_001_scenario.lua"]
    })

    msg = await read_until_command(host_proto, "game_info", uid=game_id, timeout=5)
    assert msg["validity"] == ["valid"]


@fast_forward(60)
async def test_game_info_messages(lobby_server):
    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")
    await read_until_command(host_proto, "game_info")

    # Host game
    await host_proto.send_message({
        "command": "game_host",
        "mod": "faf",
        "visibility": "public",
    })
    msg = await read_until_command(host_proto, "game_launch")
    game_id = int(msg["uid"])

    msg = await read_until_command(host_proto, "game_info")

    assert msg["hosted_at"] is None
    assert msg["launched_at"] is None

    await open_fa(host_proto)
    await read_until_command(host_proto, "HostGame", target="game")

    msg = await read_until_command(host_proto, "game_info")
    hosted_at = msg["hosted_at"]
    assert datetime.fromisoformat(hosted_at) <= datetime_now()
    assert msg["launched_at"] is None

    # Join a player
    await join_game(guest_proto, game_id)

    # Set player options
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "Team", 1],
        [host_id, "StartSpot", 1],
        [host_id, "Faction", 1],
        [host_id, "Color", 1],
        [guest_id, "Army", 2],
        [guest_id, "Team", 2],
        [guest_id, "StartSpot", 2],
        [guest_id, "Faction", 2],
        [guest_id, "Color", 2],
    )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    msg = await read_until_launched(host_proto, game_id)

    assert msg["hosted_at"] == hosted_at
    assert msg["launched_at"] <= time.time()


@fast_forward(60)
async def test_game_ended_rates_game(lobby_server):
    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")
    ratings = await get_player_ratings(host_proto, "test", "Rhiza")

    await setup_game_1v1(host_proto, host_id, guest_proto, guest_id)
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Reports results
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [1, "victory 10"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [2, "defeat -10"]
        })
    # Report GameEnded
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })

    # Check that the ratings were updated
    new_ratings = await get_player_ratings(host_proto, "test", "Rhiza")

    assert ratings["test"][0] < new_ratings["test"][0]
    assert ratings["Rhiza"][0] > new_ratings["Rhiza"][0]

    # Now disconnect both players
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    # The game should only be rated once
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(host_proto, "player_info", timeout=10)


@pytest.mark.rabbitmq
@fast_forward(30)
async def test_game_ended_broadcasts_rating_update(lobby_server, channel):
    mq_proto_all = await connect_mq_consumer(
        lobby_server,
        channel,
        "success.rating.update"
    )
    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")
    old_ratings = await get_player_ratings(host_proto, "test", "Rhiza")

    await setup_game_1v1(host_proto, host_id, guest_proto, guest_id)
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Reports results
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [1, "victory 10"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [2, "defeat -10"]
        })
    # Report GameEnded
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })

    new_persisted_ratings = await get_player_ratings(host_proto, "test", "Rhiza")

    rhiza_message = {
        "game_id": 41956,
        "player_id": 3,  # Rhiza
        "rating_type": "global",
        "new_rating_mean": new_persisted_ratings["Rhiza"][0],
        "new_rating_deviation": new_persisted_ratings["Rhiza"][1],
        "old_rating_mean": old_ratings["Rhiza"][0],
        "old_rating_deviation": old_ratings["Rhiza"][1],
        "outcome": "DEFEAT"
    }

    test_message = {
        "game_id": 41956,
        "player_id": 1,  # test
        "rating_type": "global",
        "new_rating_mean": new_persisted_ratings["test"][0],
        "new_rating_deviation": new_persisted_ratings["test"][1],
        "old_rating_mean": old_ratings["test"][0],
        "old_rating_deviation": old_ratings["test"][1],
        "outcome": "VICTORY"
    }

    expected_messages_by_id = {
        message["player_id"]: message
        for message in [rhiza_message, test_message]
    }

    first_message = await asyncio.wait_for(mq_proto_all.read_message(), timeout=5)
    second_message = await asyncio.wait_for(mq_proto_all.read_message(), timeout=5)

    first_id = first_message["player_id"]
    expected_message = expected_messages_by_id[first_id]
    assert first_message == pytest.approx(expected_message)

    second_id = second_message["player_id"]
    assert second_id != first_id
    expected_message = expected_messages_by_id[second_id]
    assert second_message == pytest.approx(expected_message)

    # Now disconnect both players
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    # There should be no further updates
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(mq_proto_all.read_message(), timeout=10)


@fast_forward(30)
async def test_double_host_message(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await proto.send_message({
        "command": "game_host",
        "mod": "faf",
        "visibility": "public",
    })
    await read_until_command(proto, "game_launch", timeout=10)

    await proto.send_message({
        "command": "game_host",
        "mod": "faf",
        "visibility": "public",
    })
    await read_until_command(proto, "game_launch", timeout=10)


@fast_forward(30)
async def test_double_join_message(lobby_server):
    _, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    _, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await host_proto.send_message({
        "command": "game_host",
        "mod": "faf",
        "visibility": "public",
    })
    msg = await client_response(host_proto)
    game_id = msg["uid"]

    await guest_proto.send_message({
        "command": "game_join",
        "uid": game_id
    })
    await read_until_command(guest_proto, "game_launch", timeout=10)

    await guest_proto.send_message({
        "command": "game_join",
        "uid": game_id
    })
    await read_until_command(guest_proto, "game_launch", timeout=10)


@fast_forward(100)
async def test_game_with_foed_player(lobby_server):
    _, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    _, _, guest_proto = await connect_and_sign_in(
        ("foed_by_test", "foe"), lobby_server
    )

    # Set up the game
    game_id = await host_game(host_proto)
    with pytest.raises(asyncio.TimeoutError):
        await join_game(guest_proto, game_id)


@fast_forward(100)
async def test_partial_game_ended_rates_game(lobby_server, tmp_user):
    """
    Test that game is rated as soon as all players have either disconnected
    or sent `GameEnded`
    """
    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guests = []
    for _ in range(3):
        user = await tmp_user("Guest")
        guest_id, _, proto = await connect_and_sign_in(
            user, lobby_server
        )
        guests.append((guest_id, user[0], proto))

    await asyncio.gather(*(
        read_until_command(proto, "game_info")
        for (_, _, proto) in guests
    ))
    ratings = await get_player_ratings(
        host_proto,
        "test",
        *(name for _, name, _ in guests)
    )

    # Set up the game
    game_id = await host_game(host_proto)
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "StartSpot", 1],
        [host_id, "Color", 1],
        [host_id, "Faction", 1],
        [host_id, "Team", 2],
    )
    for i, (guest_id, _, guest_proto) in enumerate(guests):
        await join_game(guest_proto, game_id)
        # Set player options
        await send_player_options(
            host_proto,
            [guest_id, "Army", i+2],
            [guest_id, "StartSpot", i+2],
            [guest_id, "Color", i+2],
            [guest_id, "Faction", 1],
            [guest_id, "Team", 3 if i % 2 == 0 else 2]
        )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })
    await read_until(
        host_proto,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Reports results (lazy, just the host reports. This should still work)
    for result in (
        [1, "victory 10"],
        [2, "defeat -10"],
        [3, "victory 10"],
        [4, "defeat -10"]
    ):
        await host_proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": result
        })
    # Report GameEnded
    await host_proto.send_message({
        "target": "game",
        "command": "GameEnded",
        "args": []
    })
    # Guests disconnect without sending `GameEnded`
    for i, (_, _, guest_proto) in enumerate(guests):
        await guest_proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    # Check that the ratings were updated
    new_ratings = await get_player_ratings(
        host_proto,
        "test",
        *(name for _, name, _ in guests)
    )

    assert ratings["test"][0] < new_ratings["test"][0]
    assert ratings["Guest1"][0] > new_ratings["Guest1"][0]
    assert ratings["Guest2"][0] < new_ratings["Guest2"][0]
    assert ratings["Guest3"][0] > new_ratings["Guest3"][0]

    # Now disconnect the host too
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Ended"]
    })

    # The game should only be rated once
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(host_proto, "player_info", timeout=10)


@fast_forward(100)
async def test_ladder_game_draw_bug(lobby_server, database):
    """
    This simulates the infamous "draw bug" where a player could self destruct
    their own ACU in order to kill the enemy ACU and be awarded a victory
    instead of a draw.
    """
    player1_id, proto1, player2_id, proto2 = await queue_players_for_matchmaking(lobby_server)

    msg1, msg2 = await asyncio.gather(*[
        client_response(proto) for proto in (proto1, proto2)
    ])
    game_id = msg1["uid"]
    army1 = msg1["map_position"]
    army2 = msg2["map_position"]

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
            "target": "game",
            "command": "GameState",
            "args": ["Launching"]
        })
    await read_until(
        proto1,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )

    # Player 1 ctrl-k's
    for result in (
        [army1, "defeat -10"],
        [army1, "score 1"],
        [army2, "defeat -10"]
    ):
        for proto in (proto1, proto2):
            await proto.send_message({
                "target": "game",
                "command": "GameResult",
                "args": result
            })

    for proto in (proto1, proto2):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })

    ratings = await get_player_ratings_all(
        proto1,
        "ladder1",
        "ladder2",
        old_ratings={
            "ladder1": {
                "global": (1500, 500),
                "ladder_1v1": (1500, 500),
            },
            "ladder2": {
                "global": (1500, 500),
                "ladder_1v1": (1500, 500),
            },
        }
    )

    # Both start at (1500, 500).
    # When rated as a draw the means should barely change.
    assert 0 < abs(ratings["ladder1"]["ladder_1v1"][0] - 1500.) < 1
    assert 0 < abs(ratings["ladder2"]["ladder_1v1"][0] - 1500.) < 1

    # Global rating should also be updated
    assert 0 < abs(ratings["ladder1"]["global"][0] - 1500.) < 1
    assert 0 < abs(ratings["ladder2"]["global"][0] - 1500.) < 1

    async with database.acquire() as conn:
        result = await conn.execute(
            select(game_player_stats).where(
                game_player_stats.c.gameId == game_id
            )
        )
        for row in result:
            assert row.result == GameOutcome.DEFEAT
            assert row.score == 0


@fast_forward(15)
async def test_ladder_game_not_joinable(lobby_server):
    """
    We should not be able to join AUTO_LOBBY games using the `game_join` command.
    """
    _, _, test_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    _, proto1, _, _ = await queue_players_for_matchmaking(lobby_server)
    await read_until_command(test_proto, "game_info")

    msg = await read_until_command(proto1, "game_launch")
    await open_fa(proto1)

    game_uid = msg["uid"]

    await test_proto.send_message({
        "command": "game_join",
        "uid": game_uid
    })

    msg = await read_until_command(test_proto, "notice", timeout=5)
    assert msg == {
        "command": "notice",
        "style": "error",
        "text": "The game cannot be joined in this way."
    }


@pytest.mark.flaky
@fast_forward(60)
async def test_gamestate_ended_clears_references(
    lobby_server,
    game_service,
    player_service
):
    test_id, _, test_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, rhiza_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(test_proto, "game_info")
    await read_until_command(rhiza_proto, "game_info")

    game_id = await setup_game_1v1(test_proto, test_id, rhiza_proto, rhiza_id)
    await asyncio.sleep(0.1)

    game = game_service[game_id]

    assert len(game.connections) == 2

    test = player_service[test_id]
    rhiza = player_service[rhiza_id]

    # Player leaves and sends results after
    await rhiza_proto.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })
    await rhiza_proto.send_message({
        "command": "GameResult",
        "target": "game",
        "args": [1, "victory 10"]
    })
    await asyncio.sleep(0.1)
    gc.collect()
    assert rhiza.game_connection is None
    assert len(game.connections) == 1
    assert len(game._results) == 0

    # Player sends results first and then leaves
    await test_proto.send_message({
        "command": "GameResult",
        "target": "game",
        "args": [2, "victory 10"]
    })
    await test_proto.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })

    await read_until_command(
        test_proto,
        "game_info",
        state="closed",
        num_players=0
    )
    await asyncio.sleep(0.1)
    gc.collect()
    assert test.game_connection is None
    assert len(game.connections) == 0
    assert len(game._results) == 1

    assert game_id not in game_service

    assert test.lobby_connection.game_connection is None
    assert rhiza.lobby_connection.game_connection is None


@fast_forward(30)
async def test_gamestate_ended_modifies_player_list(lobby_server):
    test_id, _, test_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, rhiza_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(test_proto, "game_info")
    await read_until_command(rhiza_proto, "game_info")

    # Set up the game
    game_id = await host_game(test_proto)
    await join_game(rhiza_proto, game_id)
    # Set player options
    await send_player_options(
        test_proto,
        [test_id, "Army", 1],
        [test_id, "Team", 1],
        [test_id, "StartSpot", 1],
        [test_id, "Faction", 1],
        [test_id, "Color", 1],
        [rhiza_id, "Army", 2],
        [rhiza_id, "Team", 1],
        [rhiza_id, "StartSpot", 2],
        [rhiza_id, "Faction", 1],
        [rhiza_id, "Color", 1],
    )

    teams = {"1": ["test", "Rhiza"]}
    teams_ids = [{"team_id": 1, "player_ids": [test_id, rhiza_id]}]
    await read_until_command(test_proto, "game_info", teams=teams, teams_ids=teams_ids)
    await read_until_command(rhiza_proto, "game_info", teams=teams, teams_ids=teams_ids)

    # Launch game, trggers another game_info message
    await test_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    msg1 = await read_until_command(test_proto, "game_info")
    msg2 = await read_until_command(rhiza_proto, "game_info")
    assert msg1["teams"] == msg2["teams"] == {"1": ["test", "Rhiza"]}
    assert msg1["teams_ids"] == msg2["teams_ids"] == [{"team_id": 1, "player_ids": [test_id, rhiza_id]}]

    # One player leaves
    await test_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Ended"]
    })

    # game_info shows only the connected player
    msg1 = await read_until_command(test_proto, "game_info")
    msg2 = await read_until_command(rhiza_proto, "game_info")
    assert msg1["teams"] == msg2["teams"] == {"1": ["Rhiza"]}
    assert msg1["teams_ids"] == msg2["teams_ids"] == [{"team_id": 1, "player_ids": [rhiza_id]}]


@pytest.mark.rabbitmq
@fast_forward(30)
async def test_game_stats_broadcasts_achievement_updates(
    lobby_server,
    channel
):
    mq_proto_ach = await connect_mq_consumer(
        lobby_server,
        channel,
        "request.achievement.update"
    )
    mq_proto_evt = await connect_mq_consumer(
        lobby_server,
        channel,
        "request.event.update"
    )

    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")

    await setup_game_1v1(host_proto, host_id, guest_proto, guest_id)

    # Report results
    # We only want achievement updates for 1 player so don't report stats for both
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [1, "victory 10"]
        })

    # Report stats
    with open("tests/data/game_stats_simple_win.json", "r") as f:
        stats = json.loads(f.read())["stats"]

    stats[0]["name"] = "test"
    stats[1]["name"] = "Rhiza"
    await host_proto.send_message({
        "target": "game",
        "command": "JsonStats",
        "args": [json.dumps({"stats": stats})]
    })

    # Achievement updates
    assert await asyncio.wait_for(mq_proto_ach.read_message(), timeout=10) == {
        "playerId": host_id,
        "achievementId": "c6e6039f-c543-424e-ab5f-b34df1336e81",  # ACH_NOVICE
        "operation": "INCREMENT",
        "steps": 1
    }
    assert await asyncio.wait_for(mq_proto_ach.read_message(), timeout=5) == {
        "playerId": host_id,
        "achievementId": "d5c759fe-a1a8-4103-888d-3ba319562867",  # ACH_JUNIOR
        "operation": "INCREMENT",
        "steps": 1
    }
    assert await asyncio.wait_for(mq_proto_ach.read_message(), timeout=5) == {
        "playerId": host_id,
        "achievementId": "6a37e2fc-1609-465e-9eca-91eeda4e63c4",  # ACH_SENIOR
        "operation": "INCREMENT",
        "steps": 1
    }
    assert await asyncio.wait_for(mq_proto_ach.read_message(), timeout=5) == {
        "playerId": host_id,
        "achievementId": "bd12277a-6604-466a-9ee6-af6908573585",  # ACH_VETERAN
        "operation": "INCREMENT",
        "steps": 1
    }
    assert await asyncio.wait_for(mq_proto_ach.read_message(), timeout=5) == {
        "playerId": host_id,
        "achievementId": "805f268c-88aa-4073-aa2b-ea30700f70d6",  # ACH_ADDICT
        "operation": "INCREMENT",
        "steps": 1
    }

    # Event updates
    assert await asyncio.wait_for(mq_proto_evt.read_message(), timeout=10) == {
        "playerId": host_id,
        "eventId": "1b900d26-90d2-43d0-a64e-ed90b74c3704",  # EVENT_UEF_PLAYS
        "count": 1
    }
    assert await asyncio.wait_for(mq_proto_evt.read_message(), timeout=10) == {
        "playerId": host_id,
        "eventId": "7be6fdc5-7867-4467-98ce-f7244a66625a",  # EVENT_UEF_WINS
        "count": 1
    }


@pytest.mark.rabbitmq
@fast_forward(30)
async def test_galactic_war_1v1_game_ended_broadcasts_army_results(
    lobby_server,
    channel
):
    mq_proto_all = await connect_mq_consumer(
        lobby_server,
        channel,
        "success.gameResults.create"
    )

    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")

    await setup_game_1v1(host_proto, host_id, guest_proto, guest_id, mod="gw")
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Report results
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [1, "victory 10"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [2, "recall defeat -5"]
        })
    # Report GameEnded
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })
    # Now disconnect both players
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    message = await asyncio.wait_for(mq_proto_all.read_message(), timeout=10)

    assert message == {
        "game_id": 41956,
        "rating_type": "global",
        "map_id": 7,
        "featured_mod": "gw",
        "sim_mod_ids": [],
        "commander_kills": {},
        "validity": "VALID",
        "teams": [
            {
                "outcome": "DEFEAT",
                "player_ids": [3],
                "army_results": [
                    {
                        "player_id": 3,
                        "army": 2,
                        "army_outcome": "DEFEAT",
                        "metadata": ["recall"],
                    },
                ]
            },
            {
                "outcome": "VICTORY",
                "player_ids": [1],
                "army_results": [
                    {
                        "player_id": 1,
                        "army": 1,
                        "army_outcome": "VICTORY",
                        "metadata": [],
                    },
                ]
            }
        ]
    }

    with pytest.raises(asyncio.TimeoutError):
        # We expect only one message to be broadcast
        await asyncio.wait_for(mq_proto_all.read_message(), timeout=10)


@pytest.mark.flaky
@pytest.mark.rabbitmq
@fast_forward(30)
async def test_galactic_war_2v1_game_ended_broadcasts_army_results(lobby_server, channel):
    mq_proto_all = await connect_mq_consumer(
        lobby_server,
        channel,
        "success.gameResults.create"
    )

    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    other_guest_id, _, other_guest_proto = await connect_and_sign_in(
        ("newbie", "password"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")
    await read_until_command(other_guest_proto, "game_info")

    # Set up the game
    game_id = await host_game(host_proto, mod="gw")
    await join_game(guest_proto, game_id)
    await join_game(other_guest_proto, game_id)
    # Set player options
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "Team", 0],
        [host_id, "StartSpot", 1],
        [host_id, "Faction", 1],
        [host_id, "Color", 1],
        [guest_id, "Army", 2],
        [guest_id, "Team", 0],
        [guest_id, "StartSpot", 2],
        [guest_id, "Faction", 1],
        [guest_id, "Color", 2],
        [other_guest_id, "Army", 3],
        [other_guest_id, "Team", 2],
        [other_guest_id, "StartSpot", 3],
        [other_guest_id, "Faction", 2],
        [other_guest_id, "Color", 3],
    )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    await read_until(
        host_proto,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Report results
    for proto in (host_proto, guest_proto, other_guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [1, "victory 10"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [2, "recall victory 5"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [3, "recall defeat -5"]
        })
    # Report GameEnded
    for proto in (host_proto, guest_proto, other_guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })
    # Now disconnect all players
    for proto in (host_proto, guest_proto, other_guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    message = await asyncio.wait_for(mq_proto_all.read_message(), timeout=10)

    assert message == {
        "commander_kills": {},
        "featured_mod": "gw",
        "game_id": 41956,
        "map_id": 7,
        "rating_type": "global",
        "sim_mod_ids": [],
        "teams": [
            {
                "army_results": [
                    {
                        "player_id": 1,
                        "army": 1,
                        "army_outcome": "VICTORY",
                        "metadata": [],
                    },
                    {
                        "player_id": 3,
                        "army": 2,
                        "army_outcome": "VICTORY",
                        "metadata": ["recall"],
                    },
                ],
                "outcome": "UNKNOWN",
                "player_ids": [1, 3]
            },
            {
                "army_results": [
                    {
                        "player_id": 6,
                        "army": 3,
                        "army_outcome": "DEFEAT",
                        "metadata": ["recall"],
                    },
                ],
                "outcome": "UNKNOWN",
                "player_ids": [6]
            },
        ],
        "validity": "UNEVEN_TEAMS_NOT_RANKED",
    }

    with pytest.raises(asyncio.TimeoutError):
        # We expect only one message to be broadcast
        await asyncio.wait_for(mq_proto_all.read_message(), timeout=10)
