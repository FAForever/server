import asyncio

import pytest
from server.db.models import game_player_stats
from sqlalchemy import select
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until, read_until_command

pytestmark = pytest.mark.asyncio


async def queue_player_for_matchmaking(user, lobby_server):
    _, _, proto = await connect_and_sign_in(user, lobby_server)
    await read_until_command(proto, 'game_info')
    await proto.send_message({
        'command': 'game_matchmaking',
        'state': 'start',
        'faction': 'uef'
    })

    return proto


async def queue_players_for_matchmaking(lobby_server):
    proto1 = await queue_player_for_matchmaking(
        ('ladder1', 'ladder1'),
        lobby_server
    )
    _, _, proto2 = await connect_and_sign_in(
        ('ladder2', 'ladder2'),
        lobby_server
    )

    await read_until_command(proto2, 'game_info')

    await proto2.send_message({
        'command': 'game_matchmaking',
        'state': 'start',
        'faction': 1  # Python client sends factions as numbers
    })

    # If the players did not match, this will fail due to a timeout error
    await read_until_command(proto1, 'match_found')
    await read_until_command(proto2, 'match_found')

    return proto1, proto2


@fast_forward(15)
async def test_game_launch_message(lobby_server):
    proto1, proto2 = await queue_players_for_matchmaking(lobby_server)

    msg1 = await read_until_command(proto1, 'game_launch')
    await proto1.send_message({
        'command': 'GameState',
        'target': 'game',
        'args': ['Idle']
    })
    await proto1.send_message({
        'command': 'GameState',
        'target': 'game',
        'args': ['Lobby']
    })
    msg2 = await read_until_command(proto2, 'game_launch')

    assert msg1['uid'] == msg2['uid']
    assert msg1['mod'] == msg2['mod'] == 'ladder1v1'
    assert msg1['mapname'] == msg2['mapname']
    assert msg1['team'] == msg2['team'] == 1
    assert msg1['faction'] == msg2['faction'] == 1  # faction 1 is uef
    assert msg1['expected_players'] == msg2['expected_players'] == 2
    assert msg1['map_position'] == 1
    assert msg2['map_position'] == 2


@fast_forward(15)
async def test_game_matchmaking_start(lobby_server, database):
    host, guest = await queue_players_for_matchmaking(lobby_server)

    # The player that queued last will be the host
    msg = await read_until_command(host, 'game_launch')
    await host.send_message({
        'command': 'GameState',
        'target': 'game',
        'args': ['Idle']
    })
    await host.send_message({
        'command': 'GameState',
        'target': 'game',
        'args': ['Lobby']
    })
    await read_until_command(host, 'game_info')

    await read_until_command(guest, 'game_launch')
    await guest.send_message({
        'command': 'GameState',
        'target': 'game',
        'args': ['Idle']
    })
    await guest.send_message({
        'command': 'GameState',
        'target': 'game',
        'args': ['Lobby']
    })
    await read_until_command(host, 'game_info')
    await read_until_command(guest, 'game_info')
    await asyncio.sleep(0.5)

    await host.send_message({
        'command': 'GameState',
        'target': 'game',
        'args': ['Launching']
    })

    # Wait for db to be updated
    await read_until(
        host, lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )
    await read_until(
        guest, lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )

    async with database.acquire() as conn:
        result = await conn.execute(select([
            game_player_stats.c.faction,
            game_player_stats.c.color,
            game_player_stats.c.team,
            game_player_stats.c.place,
        ]).where(game_player_stats.c.gameId == msg["uid"]))
        rows = await result.fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row["faction"] == 1
            assert row["color"] in (1, 2)
            assert row["team"] is not None
            assert row["place"] is not None


@fast_forward(50)
async def test_game_matchmaking_timeout(lobby_server):
    proto1, proto2 = await queue_players_for_matchmaking(lobby_server)

    # The player that queued last will be the host
    msg2 = await read_until_command(proto2, 'game_launch')
    # LEGACY BEHAVIOUR: The host does not respond with the appropriate GameState
    # so the match is cancelled. However, the client does not know how to
    # handle `game_launch_cancelled` messages so we still send `game_launch` to
    # prevent the client from showing that it is searching when it really isn't.
    msg1 = await read_until_command(proto1, 'game_launch')
    await read_until_command(proto2, 'game_launch_cancelled')
    await read_until_command(proto1, 'game_launch_cancelled')

    assert msg1['uid'] == msg2['uid']
    assert msg1['mod'] == 'ladder1v1'
    assert msg2['mod'] == 'ladder1v1'


async def test_game_matchmaking_cancel(lobby_server):
    proto = await queue_player_for_matchmaking(
        ('ladder1', 'ladder1'),
        lobby_server
    )

    await proto.send_message({
        'command': 'game_matchmaking',
        'state': 'stop',
    })

    # The server should respond with a matchmaking stop message
    msg = await read_until_command(proto, 'game_matchmaking')

    assert msg == {
        'command': 'game_matchmaking',
        'state': 'stop',
    }


@fast_forward(50)
async def test_game_matchmaking_disconnect(lobby_server):
    proto1, proto2 = await queue_players_for_matchmaking(lobby_server)
    # One player disconnects before the game has launched
    await proto1.close()

    msg = await read_until_command(proto2, 'game_launch_cancelled')

    assert msg == {'command': 'game_launch_cancelled'}


@fast_forward(100)
async def test_matchmaker_info_message(lobby_server, mocker):
    mocker.patch('server.matchmaker.pop_timer.time', return_value=1_562_000_000)

    _, _, proto = await connect_and_sign_in(
        ('ladder1', 'ladder1'),
        lobby_server
    )
    # Because the mocking hasn't taken effect on the first message we need to
    # wait for the second message
    msg = await read_until_command(proto, 'matchmaker_info')
    msg = await read_until_command(proto, 'matchmaker_info')

    assert msg == {
        'command': 'matchmaker_info',
        'queues': [
            {
                'queue_name': 'ladder1v1',
                'queue_pop_time': '2019-07-01T16:53:21+00:00',
                'boundary_80s': [],
                'boundary_75s': []
            }
        ]
    }


@fast_forward(10)
async def test_command_matchmaker_info(lobby_server, mocker):
    mocker.patch('server.matchmaker.pop_timer.time', return_value=1_562_000_000)

    _, _, proto = await connect_and_sign_in(
        ('ladder1', 'ladder1'),
        lobby_server
    )

    await read_until_command(proto, "game_info")
    # Wait for the dirty reporting to happen
    await read_until_command(proto, "matchmaker_info")

    await proto.send_message({"command": "matchmaker_info"})
    msg = await read_until_command(proto, "matchmaker_info")
    assert msg == {
        'command': 'matchmaker_info',
        'queues': [
            {
                'queue_name': 'ladder1v1',
                'queue_pop_time': '2019-07-01T16:53:21+00:00',
                'boundary_80s': [],
                'boundary_75s': []
            }
        ]
    }


@fast_forward(10)
async def test_matchmaker_info_message_on_cancel(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ('ladder1', 'ladder1'),
        lobby_server
    )

    await read_until_command(proto, 'game_info')
    await read_until_command(proto, 'matchmaker_info')

    await proto.send_message({
        'command': 'game_matchmaking',
        'state': 'start',
        'faction': 'uef'
    })

    async def read_update_msg():
        while True:
            # Update message because a new player joined the queue
            msg = await read_until_command(proto, 'matchmaker_info')

            if not msg["queues"][0]["boundary_80s"]:
                continue

            assert msg["queues"][0]["queue_name"] == "ladder1v1"
            assert len(msg["queues"][0]["boundary_80s"]) == 1

            return

    await asyncio.wait_for(read_update_msg(), 2)

    await proto.send_message({
        'command': 'game_matchmaking',
        'state': 'stop',
    })

    # Update message because we left the queue
    msg = await read_until_command(proto, 'matchmaker_info')

    assert msg["queues"][0]["queue_name"] == "ladder1v1"
    assert len(msg["queues"][0]["boundary_80s"]) == 0
