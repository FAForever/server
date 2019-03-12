import pytest

from .conftest import connect_and_sign_in, read_until
from .testclient import ClientTest


async def test_game_matchmaking(loop, lobby_server, db_engine):
    async with db_engine.acquire() as conn:
        result = await conn.execute("SELECT mean, deviation, id from ladder1v1_rating WHERE id in (1,3)")
        ratings = [(row['mean'], row['deviation'], row['id']) async for row in result]
        await conn.execute("UPDATE ladder1v1_rating SET mean=2000,deviation=500 WHERE id in (1,3)")
    _, _, proto1 = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )
    _, _, proto2 = await connect_and_sign_in(
        ('Rhiza', 'puff_the_magic_dragon'),
        lobby_server
    )

    await read_until(proto1, lambda msg: msg['command'] == 'game_info')
    await read_until(proto2, lambda msg: msg['command'] == 'game_info')

    with ClientTest(loop=loop, process_nat_packets=True, proto=proto1) as client1:
        with ClientTest(loop=loop, process_nat_packets=True, proto=proto2) as client2:
            port1, port2 = 6112, 6113
            await client1.listen_udp(port=port1)
            await client1.perform_connectivity_test(port=port1)

            await client2.listen_udp(port=port2)
            await client2.perform_connectivity_test(port=port2)

            proto1.send_message({
                'command': 'game_matchmaking',
                'state': 'start',
                'faction': 'uef'
            })
            await proto1.drain()

            proto2.send_message({
                'command': 'game_matchmaking',
                'state': 'start',
                'faction': 'uef'
            })
            await proto2.drain()

            # If the players did not match, this test will fail due to a timeout error
            msg1 = await read_until(proto1, lambda msg: msg['command'] == 'game_launch')
            msg2 = await read_until(proto2, lambda msg: msg['command'] == 'game_launch')

            assert msg1['uid'] == msg2['uid']
            assert msg1['mod'] == 'ladder1v1'
            assert msg2['mod'] == 'ladder1v1'

    async with db_engine.acquire() as conn:
        await conn.execute(
            "UPDATE ladder1v1_rating SET mean=%s,deviation=%s WHERE id =%s",
            ratings
        )
