import asyncio

from mock import call
import pytest
import config

from server import run_game_server

from tests.integration_tests.testclient import TestGPGClient

slow = pytest.mark.slow

TEST_ADDRESS = ('127.0.0.1', None)

@asyncio.coroutine
@slow
def test_public_host(loop, players, player_service, games, db):
    player = players.hosting
    nat_server, server = run_game_server(TEST_ADDRESS, player_service, games, db, loop=loop)
    server = yield from server
    with TestGPGClient(player.gamePort, loop=loop, process_nat_packets=True) as client:
        yield from client.connect(*server.sockets[0].getsockname())
        client.proto.send_GameState(['Idle'])
        client.proto.send_GameState(['Lobby'])
        yield from client.read_until('ConnectivityState')
        assert call("\x08Are you public? %s" % player.id)\
               in client.udp_messages.mock_calls
        assert call({"key": "ConnectivityState",
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
        yield from client.connect(*server.sockets[0].getsockname())
        client.proto.send_GameState(['Idle'])
        client.proto.send_GameState(['Lobby'])
        yield from client.read_until('SendNatPacket')
        assert call({"key": "SendNatPacket",
                "commands": ["%s:%s" % (config.LOBBY_IP, config.LOBBY_UDP_PORT),
                             "Hello %s" % player.id]})\
               in client.messages.mock_calls

        client.send_udp_natpacket('Hello {}'.format(player.id), '127.0.0.1', config.LOBBY_UDP_PORT)
        yield from client.read_until('ConnectivityState')
        assert call({'key': 'ConnectivityState',
                     'commands': [player.id, 'STUN']})\
               in client.messages.mock_calls
        client.proto.write_eof()
    server.close()
    nat_server.close()
    yield from server.wait_closed()
