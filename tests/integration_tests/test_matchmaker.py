import asyncio
import pytest

from .conftest import connect_and_sign_in, read_until_command

pytestmark = pytest.mark.asyncio

# Need to save the old sleep here otherwise the mocker recursively patches it
aiosleep = asyncio.sleep


async def queue_players_for_matchmaking(lobby_server):
    _, _, proto1 = await connect_and_sign_in(
        ('ladder1', 'ladder1'),
        lobby_server
    )
    _, _, proto2 = await connect_and_sign_in(
        ('ladder2', 'ladder2'),
        lobby_server
    )

    await read_until_command(proto1, 'game_info')
    await read_until_command(proto2, 'game_info')

    proto1.send_message({
        'command': 'game_matchmaking',
        'state': 'start',
        'faction': 'uef'
    })
    await proto1.drain()

    proto2.send_message({
        'command': 'game_matchmaking',
        'state': 'start',
        'faction': 1  # Python client sends factions as numbers
    })
    await proto2.drain()

    # If the players did not match, this will fail due to a timeout error
    await read_until_command(proto1, 'match_found')
    await read_until_command(proto2, 'match_found')

    return proto1, proto2


async def test_game_matchmaking(loop, lobby_server, mocker):
    mocker.patch('asyncio.sleep', side_effect=lambda _: aiosleep(0.1))
    proto1, proto2 = await queue_players_for_matchmaking(lobby_server)

    # The player that queued last will be the host
    msg2 = await read_until_command(proto2, 'game_launch')
    proto2.send_message({
        'command': 'GameState',
        'target': 'game',
        'args': ['Lobby']
    })
    msg1 = await read_until_command(proto1, 'game_launch')

    assert msg1['uid'] == msg2['uid']
    assert msg1['mod'] == 'ladder1v1'
    assert msg2['mod'] == 'ladder1v1'


async def test_matchmaker_info_message(lobby_server, mocker):
    mocker.patch('server.matchmaker.pop_timer.time', return_value=1_562_000_000)
    mocker.patch('server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX', 1)

    _, _, proto = await connect_and_sign_in(
        ('ladder1', 'ladder1'),
        lobby_server
    )
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
