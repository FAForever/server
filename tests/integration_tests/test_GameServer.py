from asyncio import coroutine, sleep
import asyncio
import time

from mock import call
import pytest
import ujson
import config

from server import run_game_server

from tests.integration_tests.testclient import TestGPGClient

slow = pytest.mark.slow

TEST_ADDRESS = ('127.0.0.1', 8000)


@coroutine
def wait_call(mock, call, timeout=0.5):
    start_time = time.time()
    yield from asyncio.sleep(0.1)
    while time.time() - start_time < timeout:
        if call in mock.mock_calls:
            return True
        yield from sleep(0.1)
    assert call in mock.mock_calls

@asyncio.coroutine
@slow
def test_public_host(loop, players, player_service, games, db):
    player = players.hosting
    nat_server, server = run_game_server(TEST_ADDRESS, player_service, games, db, loop=loop)
    server = yield from server
    with TestGPGClient(player.gamePort, loop=loop, process_nat_packets=True) as client:
        yield from client.connect('127.0.0.1', 8000)
        client.proto.send_GameState(['Idle'])
        client.proto.send_GameState(['Lobby'])
        yield from client.read_until('ConnectivityState')
        assert call("\x08Are you public? %s" % player.id)\
               in client.udp_messages.mock_calls
        assert call({"key": "ConnectivityState",
                    "legacy": [],
                    "commands": [player.id, "PUBLIC"]})\
               in client.messages.mock_calls
        client.proto.write_eof()
    server.close()
    nat_server.close()
    yield from server.wait_closed()


@asyncio.coroutine
@slow
def test_stun_host(loop, players, player_service, games, db):
    player = players.hosting
    nat_server, server = run_game_server(TEST_ADDRESS, player_service, games, db, loop=loop)
    server = yield from server
    with TestGPGClient(player.gamePort, loop=loop, process_nat_packets=False) as client:
        yield from client.connect('127.0.0.1', 8000)
        client.proto.send_GameState(['Idle'])
        client.proto.send_GameState(['Lobby'])
        yield from client.read_until('SendNatPacket')
        assert call({"key": "SendNatPacket",
                "legacy": [],
                "commands": ["%s:%s" % (config.LOBBY_IP, config.LOBBY_UDP_PORT),
                             "Hello %s" % player.id]})\
               in client.messages.mock_calls

        client.send_udp_natpacket('Hello {}'.format(player.id), '127.0.0.1', config.LOBBY_UDP_PORT)
        yield from client.read_until('ConnectivityState')
        assert call({'key': 'ConnectivityState',
                     'legacy': [],
                     'commands': [player.id, 'STUN']})\
               in client.messages.mock_calls
        client.proto.write_eof()
    server.close()
    nat_server.close()
    yield from server.wait_closed()
