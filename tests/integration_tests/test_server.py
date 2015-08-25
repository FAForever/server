import asyncio


from unittest.mock import call
import pytest
import config

from server import run_game_server, VisibilityState
from server.games import Game
from server.players import Player, PlayerState

from tests.integration_tests.testclient import TestGPGClient

slow = pytest.mark.slow

TEST_ADDRESS = ('127.0.0.1', None)

@pytest.fixture
def game_server(mocker, loop, request, player_service, game_service, db, mock_db_pool):
    player = Player(login='Foo', session=42, id=1)
    game = Game(1, game_service, host=player)
    # Evil hack to keep 'game' in memory.
    player._xgame = game
    player.game = game
    player.ip = '127.0.0.1'
    player.game_port = 6112
    player.state = PlayerState.HOSTING
    player_service.players = {1: player}

    nat_server, server = run_game_server(TEST_ADDRESS, player_service, game_service, loop)
    server = loop.run_until_complete(server)

    def fin():
        server.close()
        nat_server.close()
        loop.run_until_complete(server.wait_closed())

    request.addfinalizer(fin)
    return nat_server, server
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
def get_session(proto):
    proto.send_message({'command': 'ask_session'})
    yield from proto.drain()
    msg = yield from proto.read_message()
    return msg['session']

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

@asyncio.coroutine
def connect_and_sign_in(credentials, lobby_server):
    proto = yield from connect_client(lobby_server)
    session = yield from get_session(proto)
    yield from perform_login(proto, credentials)
    player_id = (yield from proto.read_message())['id']
    return player_id, session, proto

@asyncio.coroutine
@slow
def test_public_host(loop, game_server, lobby_server, player_service, db):
    nat_server, server = game_server

    player_id, session, proto = yield from connect_and_sign_in(('Dostya', 'vodka'), lobby_server)

    proto.send_message(dict(command='game_host',
                         mod='faf',
                         visibility=VisibilityState.to_string(VisibilityState.PUBLIC)))
    yield from proto.drain()

    with TestGPGClient(6112, loop=loop, process_nat_packets=True) as client:
        yield from client.connect(*server.sockets[0].getsockname())
        client.proto.send_gpgnet_message('Authenticate', [session, player_id])
        client.proto.send_GameState(['Idle'])
        client.proto.send_GameState(['Lobby'])
        yield from client.proto.writer.drain()
        yield from client.read_until('ConnectivityState')
        assert call("\x08Are you public? %s" % player_id)\
               in client.udp_messages.mock_calls
        assert call({"key": "ConnectivityState",
                    "commands": [player_id, "PUBLIC"]})\
               in client.messages.mock_calls
        client.proto.write_eof()


@asyncio.coroutine
@slow
def test_stun_host(loop, game_server, lobby_server, player_service, db):
    nat_server, server = game_server

    player_id, session, proto = yield from connect_and_sign_in(('Dostya', 'vodka'), lobby_server)

    proto.send_message(dict(command='game_host',
                            mod='faf',
                            visibility=VisibilityState.to_string(VisibilityState.PUBLIC)))
    yield from proto.drain()

    with TestGPGClient(6112, loop=loop, process_nat_packets=False) as client:
        yield from client.connect(*server.sockets[0].getsockname())
        client.proto.send_gpgnet_message('Authenticate', [session, player_id])
        client.proto.send_GameState(['Idle'])
        client.proto.send_GameState(['Lobby'])
        yield from client.read_until('SendNatPacket')
        assert call({"key": "SendNatPacket",
                "commands": ["%s:%s" % (config.LOBBY_IP, config.LOBBY_UDP_PORT),
                             "Hello %s" % player_id]})\
               in client.messages.mock_calls

        client.send_udp_natpacket('Hello {}'.format(player_id), '127.0.0.1', config.LOBBY_UDP_PORT)
        yield from client.read_until('ConnectivityState')
        assert call({'key': 'ConnectivityState',
                     'commands': [player_id, 'STUN']})\
               in client.messages.mock_calls
        client.proto.write_eof()
