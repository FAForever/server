import pytest

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def test_ladder_1v1_match(test_client):
    """More or less the same as the regression test version"""
    client1, _ = await test_client("test")
    client2, _ = await test_client("test2")

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
        "featured_mod": "ladder1v1",
        "sim_mods": {},
        "num_players": 0,
        "max_players": 2,
        "launched_at": None,
        "teams": {}
    }
