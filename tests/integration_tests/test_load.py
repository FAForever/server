import asyncio
import logging

import pytest
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command

pytestmark = pytest.mark.asyncio


@pytest.mark.slow
@fast_forward(300)
async def test_game_info_broadcast_on_connection_error(
    event_loop, lobby_server, tmp_user, ladder_service, game_service, caplog
):
    """
    Causes connection errors in `do_report_dirties` which in turn will cause
    closed games not to be cleaned up if the errors aren't handled properly.
    """
    # This test causes way to much logging output otherwise
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

    # Host the games
    async def host(proto):
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
