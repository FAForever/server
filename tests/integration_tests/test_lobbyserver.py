import asyncio
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


