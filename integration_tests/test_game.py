import asyncio

import pytest

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def simulate_game(host, *guests, results=[]):
    all_clients = [host] + list(guests)
    game_id = await host.host_game()
    await host.configure_joining_player(host.player_id, 1)
    for guest in guests:
        await guest.join_game(game_id)
        await host.configure_joining_player(guest.player_id, 2)

    await host.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })
    for client in all_clients:
        await client.read_until(
            lambda msg: (
                msg.get("command") == "game_info" and
                msg["host"] == "test" and
                msg["launched_at"] is not None
            )
        )

    await host.send_message({
        "target": "game",
        "command": "EnforceRating"
    })

    for client in all_clients:
        for result in results:
            await client.send_message({
                "target": "game",
                "command": "GameResult",
                "args": result
            })

    # Report GameEnded
    for client in all_clients:
        await client.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })


async def test_custom_game_1v1(test_client):
    """More or less the same as the regression test version"""
    client1, _ = await test_client("test")
    client2, _ = await test_client("test2")

    await client1.read_until_command("game_info")
    await client2.read_until_command("game_info")
    ratings = await client1.get_player_ratings("test", "test2")

    await simulate_game(client1, client2, results=[
        [2, "defeat -10"],
        [1, "victory 10"]
    ])

    # Check that the ratings were updated
    new_ratings = await client1.get_player_ratings("test", "test2")

    assert ratings["test"][0] < new_ratings["test"][0]
    assert ratings["test2"][0] > new_ratings["test2"][0]

    # Now disconnect both players
    for client in (client1, client2):
        await client.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })


async def test_custom_game_1v1_bad_result(test_client):
    """More or less the same as the regression test version"""
    client1, _ = await test_client("test")
    client2, _ = await test_client("test2")

    await client1.read_until_command("game_info")
    await client2.read_until_command("game_info")
    await client1.get_player_ratings("test", "test2")

    await simulate_game(client1, client2, results=[
        [1, "defeat -10"],
        [1, "victory 10"]
    ])

    # Check that the ratings were NOT updated
    with pytest.raises(asyncio.TimeoutError):
        await client1.get_player_ratings("test", "test2", timeout=3)

    # Now disconnect both players
    for client in (client1, client2):
        await client.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })
