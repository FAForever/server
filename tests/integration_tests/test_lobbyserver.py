import asyncio
import logging
import pytest
from server import run_lobby_server
from server.protocol import QDataStreamProtocol

slow = pytest.mark.slow

@pytest.fixture
def lobby_server(request, loop, db_pool, player_service, game_service, db):
    server = loop.run_until_complete(run_lobby_server(('127.0.0.1', None),
                                                      player_service,
                                                      game_service,
                                                      db,
                                                      loop))

    def fin():
        server.close()
        loop.run_until_complete(server.wait_closed())
    request.addfinalizer(fin)

    return server

@asyncio.coroutine
def connect_client(server):
    return QDataStreamProtocol(*(yield from asyncio.open_connection(*server.sockets[0].getsockname())))


@asyncio.coroutine
def perform_login(proto, credentials):
    login, pw = credentials
    proto.send_message({'command': 'hello',
                        'version': 0,
                        'login': login,
                        'password': pw,
                        'unique_id': 'some_id'})
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

@asyncio.coroutine
@slow
def test_server_invalid_login(loop, lobby_server):
    proto = yield from connect_client(lobby_server)
    yield from perform_login(proto, ('Cat', 'epic'))
    msg = yield from proto.read_message()
    assert msg == {'command': 'notice',
                   'style': 'error',
                   'text': 'Login not found or password incorrect. They are case sensitive.'}
    lobby_server.close()
    proto.close()
    yield from lobby_server.wait_closed()

@asyncio.coroutine
@slow
def test_server_valid_login(loop, lobby_server):
    proto = yield from connect_client(lobby_server)
    yield from perform_login(proto, ('Dostya', 'vodka'))
    msg = yield from proto.read_message()
    assert msg == {'command': 'welcome',
                   'id': 2,
                   'login': 'Dostya'}
    lobby_server.close()
    proto.close()
    yield from lobby_server.wait_closed()

@asyncio.coroutine
def test_player_info_broadcast(loop, lobby_server):
    p1 = yield from connect_client(lobby_server)
    p2 = yield from connect_client(lobby_server)

    yield from perform_login(p1, ('Dostya', 'vodka'))
    yield from p1.read_message()
    yield from perform_login(p2, ('Rhiza', 'puff_the_magic_dragon'))
    yield from p2.read_message()

    yield from read_until(p1, lambda m: 'player_info' in m.values()
                                        and any(map(lambda d: ('login', 'Rhiza') in d.items(), m['players'])))
    p1.close()
    p2.close()
