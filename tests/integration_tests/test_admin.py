import asyncio

import pytest

from .conftest import connect_and_sign_in, read_until_command

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def test_closeFA(lobby_server):
    _, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(proto1, "game_info")
    await read_until_command(proto2, "game_info")

    await proto1.send_message({
        "command": "admin",
        "action": "closeFA",
        "user_id": rhiza_id,
    })

    msg = await read_until_command(proto2, "notice")

    assert msg == {"command": "notice", "style": "kill"}


async def test_closelobby(lobby_server):
    _, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(proto1, "game_info")
    await read_until_command(proto2, "game_info")

    await proto1.send_message({
        "command": "admin",
        "action": "closelobby",
        "user_id": rhiza_id,
    })

    msg = await read_until_command(proto2, "notice")

    assert msg == {"command": "notice", "style": "kick"}


async def test_broadcast(lobby_server):
    _, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    _, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(proto1, "game_info")
    await read_until_command(proto2, "game_info")

    await proto1.send_message({
        "command": "admin",
        "action": "broadcast",
        "message": "Test server message",
    })

    msg = await read_until_command(proto2, "notice")

    assert msg == {
        "command": "notice",
        "style": "info",
        "text": "Test server message"
    }


async def test_broadcast_empty_message(lobby_server):
    _, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    _, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(proto1, "game_info")
    await read_until_command(proto2, "game_info")

    await proto1.send_message({
        "command": "admin",
        "action": "broadcast",
        "message": "",
    })

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(read_until_command(proto2, "notice"), 0.5)


async def test_join_channel(lobby_server):
    _, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(proto1, "game_info")
    await read_until_command(proto2, "game_info")

    await proto1.send_message({
        "command": "admin",
        "action": "join_channel",
        "user_ids": [rhiza_id],
        "channel": "test_channel",
    })

    msg = await read_until_command(proto2, "social")

    assert msg == {
        "command": "social",
        "autojoin": ["test_channel"]
    }
