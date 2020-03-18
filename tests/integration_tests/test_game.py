import asyncio
import logging

import pytest
from server.protocol import QDataStreamProtocol
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def host_game(proto: QDataStreamProtocol) -> int:
    await proto.send_message({
        "command": "game_host",
        "mod": "faf",
        "visibility": "public"
    })
    msg = await read_until_command(proto, "game_launch")
    game_id = int(msg["uid"])

    # Simulate FA opening
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

    return game_id


async def join_game(proto: QDataStreamProtocol, uid: int):
    await proto.send_message({
        "command": "game_join",
        "uid": uid
    })
    await read_until_command(proto, "game_launch")

    # Simulate FA opening
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


async def get_player_ratings(proto, *names):
    """
    Wait for `player_info` messages until all player names have been found.
    Then return a dictionary containing all those players ratings
    """
    ratings = {}
    while set(ratings.keys()) != set(names):
        msg = await read_until_command(proto, "player_info")
        ratings.update({
            player_info["login"]: player_info["global_rating"]
            for player_info in msg["players"]
        })
    return ratings


async def send_player_options(proto, *options):
    for option in options:
        await proto.send_message({
            "target": "game",
            "command": "PlayerOption",
            "args": list(option)
        })


@fast_forward(20)
async def test_game_ended_rates_game(lobby_server):
    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await read_until_command(host_proto, "game_info")
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")
    ratings = await get_player_ratings(host_proto, "test", "Rhiza")

    # Set up the game
    game_id = await host_game(host_proto)
    await join_game(guest_proto, game_id)
    # Set player options
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "Team", 1],
        [guest_id, "Army", 2],
        [guest_id, "Team", 1]
    )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })
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
        await asyncio.wait_for(
            read_until_command(host_proto, "player_info"),
            timeout=10
        )
