import pytest
import hashlib

from server import VisibilityState

from tests.integration_tests.testclient import TestClient

slow = pytest.mark.slow

TEST_ADDRESS = ('127.0.0.1', None)

import asyncio
import logging
import pytest
from server import run_lobby_server
from server.protocol import QDataStreamProtocol

slow = pytest.mark.slow


@pytest.fixture
def lobby_server(request, loop, db_pool, player_service, game_service):
    ctx = run_lobby_server(('127.0.0.1', None),
                           player_service,
                           game_service,
                           loop)
    player_service.is_uniqueid_exempt = lambda id: True

    def fin():
        ctx.close()
        loop.run_until_complete(ctx.wait_closed())

    request.addfinalizer(fin)

    return ctx


@asyncio.coroutine
def connect_client(server):
    return QDataStreamProtocol(*(yield from asyncio.open_connection(*server.sockets[0].getsockname())))


@asyncio.coroutine
def get_session(proto):
    proto.send_message({'command': 'ask_session', 'user_agent': 'faf-client', 'version': '0.11.16'})
    yield from proto.drain()
    msg = yield from proto.read_message()
    return msg['session']


@asyncio.coroutine
def perform_login(proto, credentials):
    login, pw = credentials
    pw_hash = hashlib.sha256(pw.encode('utf-8'))
    proto.send_message({'command': 'hello',
                        'version': '1.0.0-dev',
                        'user_agent': 'faf-client',
                        'login': login,
                        'password': pw_hash.hexdigest(),
                        'unique_id': 'some_id'
                        })
    yield from proto.drain()


@asyncio.coroutine
def read_until(proto, pred):
    while True:
        msg = yield from proto.read_message()
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


@asyncio.coroutine
@slow
def test_server_valid_login(loop, lobby_server):
    proto = yield from connect_client(lobby_server)
    yield from perform_login(proto, ('test', 'test_password'))
    msg = yield from proto.read_message()
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
    yield from lobby_server.wait_closed()


@asyncio.coroutine
def test_player_info_broadcast(loop, lobby_server):
    p1 = yield from connect_client(lobby_server)
    p2 = yield from connect_client(lobby_server)

    yield from perform_login(p1, ('test', 'test_password'))
    yield from perform_login(p2, ('Rhiza', 'puff_the_magic_dragon'))

    yield from read_until(p2,
                          lambda m: 'player_info' in m.values()
                                    and any(map(lambda d: ('login', 'test') in d.items(), m['players'])))
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

    with TestClient(loop=loop, process_nat_packets=True, proto=proto) as client:
        await client.listen_udp()
        client.send_GameState(['Idle'])
        client.send_GameState(['Lobby'])
        await client._proto.writer.drain()
