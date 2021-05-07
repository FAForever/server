# External matchmaker requests over rabbitmq
import asyncio
import json
import uuid

import pytest

from server.config import config
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, connect_mq_queue, read_until_command
from .test_game import client_response, start_search

pytestmark = pytest.mark.rabbitmq


@fast_forward(20)
async def test_valid_request_1v1(
    lobby_server,
    channel,
    message_queue_service
):
    test_id, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    success_queue = await connect_mq_queue(channel, "success.match.create")
    error_queue = await connect_mq_queue(channel, "error.match.create")

    await asyncio.gather(*(
        read_until_command(proto, "game_info")
        for proto in (proto1, proto2)
    ))

    # Include all the information we could possibly need
    correlation_id = str(uuid.uuid4())
    await message_queue_service.publish(
        config.MQ_EXCHANGE_NAME,
        "request.match.create",
        {
            "matchmaker_queue": "ladder1v1",
            "featured_mod": "ladder1v1",
            "game_name": "test VERSUS Rhiza",
            "map_name": "scmp_003",
            "participants": [
                {
                    "player_id": test_id,
                    "team": 2,
                    "slot": 1,
                    "faction": "uef"
                },
                {
                    "player_id": rhiza_id,
                    "team": 3,
                    "slot": 2,
                    "faction": "cybran"
                }
            ]
        },
        correlation_id=correlation_id
    )

    msg1, msg2 = await asyncio.gather(
        client_response(proto1),
        client_response(proto2)
    )
    assert msg1["uid"] == msg2["uid"]
    assert msg1["mapname"] == msg2["mapname"]
    assert msg1["name"] == msg2["name"]
    assert msg1["mod"] == msg2["mod"]
    assert msg1["rating_type"] == msg2["rating_type"]
    assert msg1["expected_players"] == msg2["expected_players"]
    assert "game_options" not in msg1 and "game_options" not in msg2

    assert msg1["mapname"] == "scmp_003"
    assert msg1["name"] == "test VERSUS Rhiza"
    assert msg1["mod"] == "ladder1v1"
    assert msg1["rating_type"] == "ladder_1v1"
    assert msg1["expected_players"] == 2

    assert msg1["team"] == 2
    assert msg1["map_position"] == 1
    assert msg1["faction"] == 1

    assert msg2["team"] == 3
    assert msg2["map_position"] == 2
    assert msg2["faction"] == 3

    await proto1.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    message = await success_queue.iterator(timeout=5).__anext__()
    assert message.correlation_id == correlation_id
    assert json.loads(message.body.decode()) == {
        "game_id": msg1["uid"]
    }
    assert await error_queue.get(fail=False) is None


@fast_forward(20)
async def test_valid_request_1v1_game_options(
    lobby_server,
    channel,
    message_queue_service
):
    test_id, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    success_queue = await connect_mq_queue(channel, "success.match.create")
    error_queue = await connect_mq_queue(channel, "error.match.create")

    await asyncio.gather(*(
        read_until_command(proto, "game_info")
        for proto in (proto1, proto2)
    ))

    # Include all the information we could possibly need
    correlation_id = str(uuid.uuid4())
    await message_queue_service.publish(
        config.MQ_EXCHANGE_NAME,
        "request.match.create",
        {
            "matchmaker_queue": "ladder1v1",
            "featured_mod": "ladder1v1",
            "game_name": "test VERSUS Rhiza",
            "map_name": "scmp_003",
            "participants": [
                {
                    "player_id": test_id,
                    "team": 2,
                    "slot": 1,
                    "faction": "uef"
                },
                {
                    "player_id": rhiza_id,
                    "team": 3,
                    "slot": 2,
                    "faction": "cybran"
                }
            ],
            "game_options": {
                "Share": "ShareUntilDeath",
                "RestrictedCategories": ["T3", "T4", "SUBS", "PARAGON"],
            }
        },
        correlation_id=correlation_id
    )

    msg1, msg2 = await asyncio.gather(
        client_response(proto1),
        client_response(proto2)
    )
    assert msg1["game_options"] == msg2["game_options"]

    assert msg1["game_options"] == {
        "Share": "ShareUntilDeath",
        "RestrictedCategories": ["T3", "T4", "SUBS", "PARAGON"],
    }

    await proto1.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    message = await success_queue.iterator(timeout=5).__anext__()
    assert message.correlation_id == correlation_id
    assert json.loads(message.body.decode()) == {
        "game_id": msg1["uid"]
    }
    assert await error_queue.get(fail=False) is None


@fast_forward(10)
async def test_invalid_request_empty(
    ladder_service,
    channel,
    message_queue_service,
):
    del ladder_service

    success_queue = await connect_mq_queue(channel, "success.match.create")
    error_queue = await connect_mq_queue(channel, "error.match.create")

    correlation_id = str(uuid.uuid4())
    await message_queue_service.publish(
        config.MQ_EXCHANGE_NAME,
        "request.match.create",
        {
            # Empty payload
        },
        correlation_id=correlation_id
    )

    message = await error_queue.iterator(timeout=5).__anext__()
    assert message.correlation_id == correlation_id
    assert json.loads(message.body.decode()) == {
        "error_code": "invalid_request",
        "args": [
            {"message": "missing 'map_name'"},
        ]
    }
    assert await success_queue.get(fail=False) is None


@fast_forward(10)
async def test_invalid_request_missing_queue_and_featured_mod(
    ladder_service,
    channel,
    message_queue_service,
):
    del ladder_service

    success_queue = await connect_mq_queue(channel, "success.match.create")
    error_queue = await connect_mq_queue(channel, "error.match.create")

    correlation_id = str(uuid.uuid4())
    await message_queue_service.publish(
        config.MQ_EXCHANGE_NAME,
        "request.match.create",
        {
            "game_name": "Test bad game",
            "map_name": "scmp_003",
            "participants": [],
        },
        correlation_id=correlation_id
    )

    message = await error_queue.iterator(timeout=5).__anext__()
    assert message.correlation_id == correlation_id
    assert json.loads(message.body.decode()) == {
        "error_code": "invalid_request",
        "args": [
            {"message": "missing 'featured_mod'"},
        ]
    }
    assert await success_queue.get(fail=False) is None


@fast_forward(10)
async def test_invalid_request_invalid_queue_name(
    ladder_service,
    channel,
    message_queue_service,
):
    del ladder_service

    success_queue = await connect_mq_queue(channel, "success.match.create")
    error_queue = await connect_mq_queue(channel, "error.match.create")

    correlation_id = str(uuid.uuid4())
    await message_queue_service.publish(
        config.MQ_EXCHANGE_NAME,
        "request.match.create",
        {
            "matchmaker_queue": "bad_queue_name",
            "game_name": "Test bad game",
            "map_name": "scmp_003",
            "participants": [],
        },
        correlation_id=correlation_id
    )

    message = await error_queue.iterator(timeout=5).__anext__()
    assert message.correlation_id == correlation_id
    assert json.loads(message.body.decode()) == {
        "error_code": "invalid_request",
        "args": [
            {"message": "invalid queue 'bad_queue_name'"},
        ],
    }
    assert await success_queue.get(fail=False) is None


@fast_forward(10)
async def test_invalid_request_empty_participants(
    ladder_service,
    channel,
    message_queue_service
):
    del ladder_service

    success_queue = await connect_mq_queue(channel, "success.match.create")
    error_queue = await connect_mq_queue(channel, "error.match.create")

    correlation_id = str(uuid.uuid4())
    await message_queue_service.publish(
        config.MQ_EXCHANGE_NAME,
        "request.match.create",
        {
            "matchmaker_queue": "ladder1v1",
            "game_name": "Test bad game",
            "map_name": "scmp_003",
            "participants": [],
        },
        correlation_id=correlation_id
    )

    message = await error_queue.iterator(timeout=5).__anext__()
    assert message.correlation_id == correlation_id
    assert json.loads(message.body.decode()) == {
        "error_code": "invalid_request",
        "args": [
            {"message": "empty participants"},
        ],
    }
    assert await success_queue.get(fail=False) is None


@fast_forward(10)
async def test_player_offline(
    lobby_server,
    channel,
    message_queue_service
):
    rhiza_id, _, proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    success_queue = await connect_mq_queue(channel, "success.match.create")
    error_queue = await connect_mq_queue(channel, "error.match.create")

    await read_until_command(proto, "game_info")

    # Include all the information we could possibly need
    correlation_id = str(uuid.uuid4())
    await message_queue_service.publish(
        config.MQ_EXCHANGE_NAME,
        "request.match.create",
        {
            "matchmaker_queue": "ladder1v1",
            "game_name": "test VERSUS Rhiza",
            "map_name": "scmp_003",
            "participants": [
                {
                    "player_id": 1,
                    "team": 2,
                    "slot": 1,
                    "faction": "uef"
                },
                {
                    "player_id": rhiza_id,
                    "team": 3,
                    "slot": 2,
                    "faction": "cybran"
                }
            ]
        },
        correlation_id=correlation_id
    )

    message = await error_queue.iterator(timeout=5).__anext__()
    assert message.correlation_id == correlation_id
    assert json.loads(message.body.decode()) == {
        "error_code": "players_not_found", "args": [{"player_id": 1}]
    }
    assert await success_queue.get(fail=False) is None


@fast_forward(10)
async def test_player_already_searching(
    lobby_server,
    channel,
    message_queue_service
):
    rhiza_id, _, proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    success_queue = await connect_mq_queue(channel, "success.match.create")
    error_queue = await connect_mq_queue(channel, "error.match.create")

    await read_until_command(proto, "game_info")
    await start_search(proto, "ladder1v1")

    correlation_id = str(uuid.uuid4())
    await message_queue_service.publish(
        config.MQ_EXCHANGE_NAME,
        "request.match.create",
        {
            "featured_mod": "faf",
            "game_name": "Rhiza solo game",
            "map_name": "scmp_003",
            "participants": [
                {
                    "player_id": rhiza_id,
                    "team": 3,
                    "slot": 2,
                    "faction": "cybran"
                }
            ]
        },
        correlation_id=correlation_id
    )

    message = await error_queue.iterator(timeout=5).__anext__()
    assert message.correlation_id == correlation_id
    assert json.loads(message.body.decode()) == {
        "error_code": "invalid_state", "args": [
            {"player_id": rhiza_id, "state": "SEARCHING_LADDER"},
        ]
    }
    assert await success_queue.get(fail=False) is None


@fast_forward(100)
async def test_players_dont_connect(
    lobby_server,
    channel,
    message_queue_service
):
    test_id, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    success_queue = await connect_mq_queue(channel, "success.match.create")
    error_queue = await connect_mq_queue(channel, "error.match.create")

    await asyncio.gather(*(
        read_until_command(proto, "game_info")
        for proto in (proto1, proto2)
    ))

    # Include all the information we could possibly need
    correlation_id = str(uuid.uuid4())
    await message_queue_service.publish(
        config.MQ_EXCHANGE_NAME,
        "request.match.create",
        {
            "matchmaker_queue": "ladder1v1",
            "featured_mod": "faf",
            "game_name": "test VERSUS Rhiza",
            "map_name": "scmp_003",
            "participants": [
                {
                    "player_id": test_id,
                    "team": 2,
                    "slot": 1,
                    "faction": "aeon"
                },
                {
                    "player_id": rhiza_id,
                    "team": 3,
                    "slot": 2,
                    "faction": "seraphim"
                }
            ]
        },
        correlation_id=correlation_id
    )

    msg = await client_response(proto1)
    assert msg["faction"] == 2
    # Mod field sould override the mod from queue
    assert msg["mod"] == "faf"

    message = await error_queue.iterator(timeout=85).__anext__()
    assert message.correlation_id == correlation_id
    assert json.loads(message.body.decode()) == {
        "error_code": "launch_failed", "args": [{"player_id": rhiza_id}]
    }
    assert await success_queue.get(fail=False) is None
