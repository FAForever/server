import asyncio

import pytest
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command

pytestmark = pytest.mark.asyncio


async def queue_players_for_matchmaking(lobby_server):
    res = await asyncio.gather(*[
        connect_and_sign_in(
            (f"ladder{i}",) * 2,
            lobby_server
        )
        for i in range(1, 5)
    ])
    protos = [proto for _, _, proto in res]

    await asyncio.gather(*[
        read_until_command(proto, "game_info") for proto in protos
    ])

    await asyncio.gather(*[
        proto.send_message({
            "command": "game_matchmaking",
            "state": "start",
            "faction": "uef",
            "mod": "ladder2v2"
        })
        for proto in protos
    ])

    # If the players did not match, this will fail due to a timeout error
    await asyncio.gather(*[
        read_until_command(proto, "match_found") for proto in protos
    ])

    return protos


@fast_forward(5)
async def test_game_matchmaking(lobby_server):
    protos = await queue_players_for_matchmaking(lobby_server)

    async def client_response(proto):
        msg = await read_until_command(proto, "game_launch")
        # Ensures that the game enters the `LOBBY` state
        await proto.send_message({
            "command": "GameState",
            "target": "game",
            "args": ["Idle"]
        })
        # Ensures that the game is considered hosted
        await proto.send_message({
            "command": "GameState",
            "target": "game",
            "args": ["Lobby"]
        })
        return msg

    msgs = await asyncio.gather(*[client_response(proto) for proto in protos])

    uid = set(msg["uid"] for msg in msgs)
    assert len(uid) == 1
    for msg in msgs:
        assert msg["init_mode"] == 1
        assert "None" not in msg["name"]
        # TODO: Make a 'ladder2v2' mod?
        assert msg["mod"] == "ladder2v2"
        assert msg["expected_players"] == 4
        assert msg["team"] in (2, 3)
        assert msg["map_position"] in (1, 2, 3, 4)
        assert msg["faction"] == 1


@fast_forward(50)
async def test_game_matchmaking_timeout(lobby_server):
    protos = await queue_players_for_matchmaking(lobby_server)

    # We don't send the `GameState: Lobby` command so the game should time out
    await asyncio.gather(*[
        read_until_command(proto, "match_cancelled") for proto in protos
    ])