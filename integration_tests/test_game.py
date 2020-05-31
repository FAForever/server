import asyncio

import pytest

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def simulate_game(host, *guests, results=[]):
    all_clients = [host] + list(guests)
    await simulate_game_launch(host, *guests)

    await simulate_result_reports(host, *guests, results=results)

    # Report GameEnded
    for client in all_clients:
        await client.send_gpg_command("GameState", "Ended")


async def simulate_game_launch(host, *guests):
    all_clients = [host] + list(guests)
    game_id = await host.host_game()
    await host.configure_joining_player(host.player_id, 1)
    for guest in guests:
        await guest.join_game(game_id)
        await host.configure_joining_player(guest.player_id, 2)

    await host.send_gpg_command("GameState", "Launching")

    for client in all_clients:
        await client.read_until(
            lambda msg: (
                msg.get("command") == "game_info" and
                msg["host"] == "test" and
                msg["launched_at"] is not None
            )
        )


async def simulate_result_reports(host, *guests, results=[]):
    all_clients = [host] + list(guests)

    await host.send_gpg_command("EnforceRating")

    for result in results:
        for client in all_clients:
            await client.send_gpg_command("GameResult", *result)


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

    # Now disconnect both players
    for client in (client1, client2):
        await client.send_gpg_command("GameState", "Ended")

    assert ratings["test"][0] < new_ratings["test"][0]
    assert ratings["test2"][0] > new_ratings["test2"][0]


async def test_custom_game_1v1_bad_result(test_client):
    client1, _ = await test_client("test")
    client2, _ = await test_client("test2")

    await client1.read_until_command("game_info")
    await client2.read_until_command("game_info")
    await client1.get_player_ratings("test", "test2")

    await simulate_game(client1, client2, results=[
        [1, "defeat -10"],
        [1, "victory 10"]
    ])

    # Now disconnect both players
    for client in (client1, client2):
        await client.send_gpg_command("GameState", "Ended")

    # Check that the ratings were NOT updated
    with pytest.raises(asyncio.TimeoutError):
        await client1.get_player_ratings("test", "test2", timeout=3)


async def test_custom_game_1v1_game_stats(test_client, json_stats_1v1):
    client1, _ = await test_client("test")
    client2, _ = await test_client("test2")

    await client1.read_until_command("game_info")
    await client2.read_until_command("game_info")

    await simulate_game(client1, client2, results=[
        [1, "victory 10"],
        [2, "defeat -10"]
    ])

    stats = json_stats_1v1("test", "test2")
    for client in (client1, client2):
        await client.send_message({
            "target": "game",
            "command": "JsonStats",
            "args": [stats]
        })

    # Now disconnect both players
    for client in (client1, client2):
        await client.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    await client1.read_until_command("updated_achievements", timeout=10)
    await client2.read_until_command("updated_achievements", timeout=2)


async def test_custom_game_1v1_extra_gameresults(test_client):
    """Clients can send bad game results when a player leaves the game early"""
    client1, _ = await test_client("test")
    client2, _ = await test_client("test2")

    await client1.read_until_command("game_info")
    await client2.read_until_command("game_info")
    ratings = await client1.get_player_ratings("test", "test2")

    await simulate_game_launch(client1, client2)

    # Just for testing purposes
    await client1.send_gpg_command("EnforceRating")

    # One player leaves prematurely
    await client1.send_gpg_command("GameState", "Ended")
    await client1.send_gpg_command("GameResult", 2, "defeat -10")

    await client2.send_gpg_command("GameResult", 1, "defeat -10")
    await client2.send_gpg_command("GameResult", 2, "victory 10")
    await client2.send_gpg_command("GameEnded")

    # Check that the ratings were updated
    new_ratings = await client1.get_player_ratings("test", "test2")

    # Now disconnect the other player
    await client2.send_gpg_command("GameState", "Ended")

    assert ratings["test"][0] > new_ratings["test"][0]
    assert ratings["test2"][0] < new_ratings["test2"][0]
