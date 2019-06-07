import pytest
from server import VisibilityState

from .conftest import connect_client, perform_login, read_until, connect_and_sign_in
from .testclient import ClientTest

TEST_ADDRESS = ('127.0.0.1', None)


async def test_server_invalid_login(loop, lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ('Cat', 'epic'))
    msg = await proto.read_message()
    assert msg == {'command': 'authentication_failed',
                   'text': 'Login not found or password incorrect. They are case sensitive.'}
    proto.close()


async def test_server_ban(loop, lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ('Dostya', 'vodka'))
    msg = await proto.read_message()
    assert msg == {
        'command': 'notice',
        'style': 'error',
        'text': 'You are banned from FAF for 981 years.\n Reason :\n Test permanent ban'}
    proto.close()


async def test_server_valid_login(loop, lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ('test', 'test_password'))
    msg = await proto.read_message()
    assert msg == {'command': 'welcome',
                   'me': {'clan': '678',
                          'country': '',
                          'global_rating': [2000.0, 125.0],
                          'id': 1,
                          'ladder_rating': [2000.0, 125.0],
                          'login': 'test',
                          'number_of_games': 5},
                   'id': 1,
                   'login': 'test'}
    lobby_server.close()
    proto.close()
    await lobby_server.wait_closed()


async def test_player_info_broadcast(loop, lobby_server):
    p1 = await connect_client(lobby_server)
    p2 = await connect_client(lobby_server)

    await perform_login(p1, ('test', 'test_password'))
    await perform_login(p2, ('Rhiza', 'puff_the_magic_dragon'))

    await read_until(
        p2, lambda m: 'player_info' in m.values()
        and any(map(lambda d: ('login', 'test') in d.items(), m['players']))
    )
    p1.close()
    p2.close()


@pytest.mark.slow
async def test_public_host(loop, lobby_server, player_service):
    # TODO: This test can't fail, why is it here?
    player_id, session, proto = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )

    await read_until(proto, lambda msg: msg['command'] == 'game_info')

    with ClientTest(loop=loop, process_nat_packets=True, proto=proto) as client:
        proto.send_message({
            'command': 'game_host',
            'mod': 'faf',
            'visibility': VisibilityState.to_string(VisibilityState.PUBLIC)
        })
        await proto.drain()

        client.send_GameState(['Idle'])
        client.send_GameState(['Lobby'])
        await client._proto.writer.drain()


@pytest.mark.slow
async def test_host_missing_fields(loop, lobby_server, player_service):
    player_id, session, proto = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )

    await read_until(proto, lambda msg: msg['command'] == 'game_info')

    with ClientTest(loop=loop, process_nat_packets=True, proto=proto) as client:
        proto.send_message({
            'command': 'game_host',
            'mod': '',
            'visibility': VisibilityState.to_string(VisibilityState.PUBLIC),
            'title': ''
        })
        await proto.drain()

        msg = await read_until(proto, lambda msg: msg['command'] == 'game_info')

        assert msg['title'] == 'test&#x27;s game'
        assert msg['mapname'] == 'scmp_007'
        assert msg['map_file_path'] == 'maps/scmp_007.zip'
        assert msg['featured_mod'] == 'faf'
