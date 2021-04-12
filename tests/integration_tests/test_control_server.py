import asyncio

import aiohttp
import pytest

from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


def listify(obj: dict):
    for k, v in obj.items():
        if isinstance(v, tuple):
            obj[k] = list(v)
        elif isinstance(v, dict):
            obj[k] = listify(v)
    return obj


@fast_forward(3)
async def test_players(control_server, lobby_server, player_service):
    test_id, _, _ = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )

    url = f"http://{control_server.host}:{control_server.port}/players"
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        async with session.get(url) as resp:
            data = await resp.json()

            assert data == [listify(player_service[test_id].to_dict())]


@fast_forward(3)
async def test_games(control_server, lobby_server, game_service):
    test_id, _, proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await proto.send_message({
        "command": "game_host",
        "mod": "faf",
        "visibility": "public"
    })
    msg = await read_until_command(proto, "game_launch")
    await proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Idle"]
    })
    await proto.send_message({
        "target": "game",
        "command": "PlayerOption",
        # Send this as a string because json object keys can only be strings.
        # This makes our assertion check easier.
        "args": [test_id, "Team", "1"]
    })

    url = f"http://{control_server.host}:{control_server.port}/games"
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        async with session.get(url) as resp:
            data = await resp.json()

            assert data == [listify(game_service[msg["uid"]].to_dict())]
