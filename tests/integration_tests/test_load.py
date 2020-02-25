import asyncio
import logging

import pytest
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio

###############################################################################
#                                   HELPERS                                   #
###############################################################################


async def host(proto):
    """Send a sequence of commands to simulate hosting a game"""
    await proto.send_message({
        "command": "game_host",
        "title": "A dirty game",
        "mod": "faf",
        "visibility": "public"
    })
    msg = await read_until_command(proto, "game_launch")

    # Pretend like ForgedAlliance.exe opened
    await proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Idle"]
    })
    return msg


async def write_without_reading(proto):
    # It takes quite a lot of spamming for the backpressure handling to take
    # affect.
    for _ in range(20_000):
        await proto.send_message({
            "command": "matchmaker_info",
            "This is just to increase the message size": "DATA" * 1024
        })

    pytest.fail("The server did not apply backpressure to a spammer")


@pytest.mark.slow
@fast_forward(300)
async def test_game_info_broadcast_on_connection_error(
    event_loop, lobby_server, tmp_user, ladder_service, game_service, caplog
):
    """
    Causes connection errors in `do_report_dirties` which in turn will cause
    closed games not to be cleaned up if the errors aren't handled properly.
    """
    # This test causes way too much logging output otherwise
    caplog.set_level(logging.WARNING)

    NUM_HOSTS = 10
    NUM_PLAYERS_DC = 20
    NUM_TIMES_DC = 10

    # Number of times that games will be rehosted
    NUM_GAME_REHOSTS = 20

    # Set up our game hosts
    host_protos = []
    for _ in range(NUM_HOSTS):
        _, _, proto = await connect_and_sign_in(
            await tmp_user("Host"), lobby_server
        )
        host_protos.append(proto)
    await asyncio.gather(*(
        read_until_command(proto, "game_info")
        for proto in host_protos
    ))

    # Set up our players that will disconnect
    dc_players = [await tmp_user("Disconnecter") for _ in range(NUM_PLAYERS_DC)]

    async def spam_game_changes(proto):
        for _ in range(NUM_GAME_REHOSTS):
            # Host
            await host(proto)
            await asyncio.sleep(0.1)
            # Leave the game
            await proto.send_message({
                "target": "game",
                "command": "GameState",
                "args": ["Ended"]
            })

    tasks = []
    for proto in host_protos:
        tasks.append(spam_game_changes(proto))

    async def do_dc_player(player):
        for _ in range(NUM_TIMES_DC):
            _, _, proto = await connect_and_sign_in(player, lobby_server)
            await read_until_command(proto, "game_info")
            await asyncio.sleep(0.1)
            proto.close()

    async def do_dc_players():
        await asyncio.gather(*(
            do_dc_player(player)
            for player in dc_players
        ))

    tasks.append(do_dc_players())

    # Let the guests cause a bunch of broadcasts to happen while the other
    # players are disconnecting
    await asyncio.gather(*tasks)

    # Wait for games to be cleaned up
    for proto in host_protos:
        proto.close()
    ladder_service.shutdown_queues()

    # Wait for games to time out if they need to
    await asyncio.sleep(35)

    # Ensure that the connection errors haven't prevented games from being
    # cleaned up.
    assert len(game_service.all_games) == 0


@fast_forward(50)
async def test_backpressure_handling(lobby_server, tmp_user, caplog):
    # TRACE will be spammed with thousands of messages
    caplog.set_level(logging.DEBUG)

    _, _, proto = await connect_and_sign_in(
        await tmp_user("Malicious"), lobby_server
    )
    # Set our local buffer size to 0 so that we can detect immediately when the
    # server has started applying backpressure
    proto.writer.transport.set_write_buffer_limits(high=0)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(write_without_reading(proto), 10)


@fast_forward(50)
async def test_backpressure_broadcast(lobby_server, caplog):
    # TRACE will be spammed with thousands of messages
    caplog.set_level(logging.DEBUG)

    NUM_GAME_REHOSTS = 20

    _, _, proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )

    _, _, proto2 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    # Set our local buffer size to 0 so that we can detect immediately when the
    # server has started applying backpressure
    proto2.writer.transport.set_write_buffer_limits(high=0)

    async def normal_user(proto):
        for _ in range(NUM_GAME_REHOSTS):
            # Trigger a broadcast
            await host(proto)
            # Make sure we receive the broadcast
            await read_until_command(proto, "game_info")
            # Leave the game
            await proto.send_message({
                "target": "game",
                "command": "GameState",
                "args": ["Ended"]
            })

    # Start the spamming
    asyncio.ensure_future(write_without_reading(proto2))

    # Make sure that a normal user still gets their broadcasts.
    # Improper handling will cause a TimeoutError
    await asyncio.wait_for(normal_user(proto), NUM_GAME_REHOSTS * 2)
