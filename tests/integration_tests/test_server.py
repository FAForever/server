import asyncio
import hashlib
import logging

import pytest
from server import VisibilityState, run_lobby_server
from server.protocol import QDataStreamProtocol
from tests.integration_tests.testclient import ClientTest

slow = pytest.mark.slow

TEST_ADDRESS = ('127.0.0.1', None)


@pytest.fixture
def lobby_server(request, loop, db_engine, player_service, game_service, geoip_service, matchmaker_queue):
    ctx = run_lobby_server(
        address=('127.0.0.1', None),
        geoip_service=geoip_service,
        player_service=player_service,
        games=game_service,
        matchmaker_queue=matchmaker_queue,
        loop=loop
    )
    player_service.is_uniqueid_exempt = lambda id: True

    def fin():
        ctx.close()
        loop.run_until_complete(ctx.wait_closed())

    request.addfinalizer(fin)

    return ctx


async def connect_client(server):
    return QDataStreamProtocol(
        *(await asyncio.open_connection(*server.sockets[0].getsockname()))
    )


async def get_session(proto):
    proto.send_message({'command': 'ask_session', 'user_agent': 'faf-client', 'version': '0.11.16'})
    await proto.drain()
    msg = await proto.read_message()

    return msg['session']


async def perform_login(proto, credentials):
    login, pw = credentials
    pw_hash = hashlib.sha256(pw.encode('utf-8'))
    proto.send_message({
        'command': 'hello',
        'version': '1.0.0-dev',
        'user_agent': 'faf-client',
        'login': login,
        'password': pw_hash.hexdigest(),
        'unique_id': 'some_id'
    })
    await proto.drain()


async def read_until(proto, pred):
    while True:
        msg = await proto.read_message()
        try:
            if pred(msg):
                return msg
        except (KeyError, ValueError):
            logging.getLogger().info("read_until predicate raised during message: {}".format(msg))
            pass


@slow
async def test_server_invalid_login(loop, lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ('Cat', 'epic'))
    msg = await proto.read_message()
    assert msg == {'command': 'authentication_failed',
                   'text': 'Login not found or password incorrect. They are case sensitive.'}
    proto.close()


@slow
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


async def connect_and_sign_in(credentials, lobby_server):
    proto = await connect_client(lobby_server)
    session = await get_session(proto)
    await perform_login(proto, credentials)
    hello = await proto.read_message()
    player_id = hello['id']
    return player_id, session, proto


@slow
async def test_public_host(loop, lobby_server, player_service):
    player_id, session, proto = await connect_and_sign_in(('test', 'test_password'),
                                                          lobby_server)

    proto.send_message(dict(command='game_host',
                            mod='faf',
                            visibility=VisibilityState.to_string(VisibilityState.PUBLIC)))
    await proto.drain()

    with ClientTest(loop=loop, process_nat_packets=True, proto=proto) as client:
        await client.listen_udp()
        client.send_GameState(['Idle'])
        client.send_GameState(['Lobby'])
        await client._proto.writer.drain()
