import asyncio
import random

import pytest

from .test_game import simulate_result_reports

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def test_ladder_1v1_match(client_factory):
    """More or less the same as the regression test version"""
    client1, _ = await client_factory.login("test")
    client2, _ = await client_factory.login("test2")

    await client1.read_until_command("game_info")
    await client2.read_until_command("game_info")

    await client1.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef"
    })

    await client2.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "seraphim"
    })

    await client1.read_until_command("match_found")
    await client2.read_until_command("match_found")

    msg1 = await client1.read_until_command("game_info")
    msg2 = await client2.read_until_command("game_info")

    assert msg1 == msg2
    assert msg1["mapname"]
    assert msg1["map_file_path"]
    assert (msg1["host"], msg1["title"]) in (
        ("test", "test Vs test2"),
        ("test2", "test2 Vs test")
    )

    del msg1["mapname"]
    del msg1["map_file_path"]
    del msg1["title"]
    del msg1["uid"]
    del msg1["host"]

    assert msg1 == {
        "command": "game_info",
        "visibility": "public",
        "password_protected": False,
        "state": "closed",
        "game_type": "matchmaker",
        "featured_mod": "ladder1v1",
        "sim_mods": {},
        "num_players": 0,
        "max_players": 2,
        "launched_at": None,
        "rating_type": "ladder_1v1",
        "rating_min": None,
        "rating_max": None,
        "enforce_rating_range": False,
        "teams": {}
    }


async def test_ladder_1v1_game(client_factory):
    """More or less the same as the regression test version"""
    client1, _ = await client_factory.login("test")
    client2, _ = await client_factory.login("test2")

    await client1.read_until_command("game_info")
    await client2.read_until_command("game_info")

    ratings = await client1.get_player_ratings(
        "test",
        "test2",
        rating_type="ladder_1v1"
    )

    await client1.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef"
    })

    await client2.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "seraphim"
    })

    player_positions = {}

    async def handle_game_launch(client):
        msg = await client.read_until_command("game_launch")
        await client.open_fa()

        player_positions[client.player_name] = msg["map_position"]
        if msg["map_position"] == 1:
            # player is host
            peer_msg = await client.read_until_command("ConnectToPeer")
            peer_id = peer_msg["args"][1]
            await client.configure_joining_player(peer_id, 2)
            await client.send_gpg_command("GameState", "Launching")
            await client.read_until_game_launch(msg["uid"])

    await asyncio.gather(
        handle_game_launch(client1),
        handle_game_launch(client2)
    )

    if random.random() < 0.5:
        winner = client1.player_name
        loser = client2.player_name
    else:
        winner = client2.player_name
        loser = client1.player_name

    await simulate_result_reports(client1, client2, results=[
        [player_positions[winner], "victory 10"],
        [player_positions[loser], "defeat -10"]
    ])

    for client in (client1, client2):
        await client.send_gpg_command("GameState", "Ended")

    new_ratings = await client1.get_player_ratings(
        "test",
        "test2",
        rating_type="ladder_1v1"
    )

    assert ratings[winner][0] < new_ratings[winner][0]
    assert ratings[loser][0] > new_ratings[loser][0]


async def test_multiqueue(client_factory):
    client1, _ = await client_factory.login("test")
    client2, _ = await client_factory.login("test2")

    await client1.join_queue("tmm2v2")

    for client in (client1, client2):
        await client.join_queue("ladder1v1")

    await client1.read_until_command("match_found", timeout=60)
    msg1 = await client1.read_until_command("search_info")
    msg2 = await client1.read_until_command("search_info")

    assert {
        "command": "search_info",
        "queue_name": "tmm2v2",
        "state": "stop"
    } in (msg1, msg2)

    assert {
        "command": "search_info",
        "queue_name": "ladder1v1",
        "state": "stop"
    } in (msg1, msg2)
