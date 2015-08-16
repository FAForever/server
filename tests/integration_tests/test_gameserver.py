import asyncio


from unittest.mock import call
import pytest
import config

from server import run_game_server
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

@asyncio.coroutine
@slow
def test_public_host(loop, game_server, players, player_service, db):
    player = players.hosting
    nat_server, server = game_server
    with TestGPGClient(player.game_port, loop=loop, process_nat_packets=True) as client:
        yield from client.connect(*server.sockets[0].getsockname())
        client.proto.send_gpgnet_message('Authenticate', ['42', '1'])
        client.proto.send_GameState(['Idle'])
        client.proto.send_GameState(['Lobby'])
        yield from client.proto.writer.drain()
        yield from client.read_until('ConnectivityState')
        assert call("\x08Are you public? %s" % player.id)\
               in client.udp_messages.mock_calls
        assert call({"key": "ConnectivityState",
                    "commands": [player.id, "PUBLIC"]})\
               in client.messages.mock_calls
        client.proto.write_eof()


@asyncio.coroutine
@slow
def test_stun_host(loop, game_server, players, player_service, db):
    player = players.hosting
    nat_server, server = game_server
    with TestGPGClient(player.game_port, loop=loop, process_nat_packets=False) as client:
        yield from client.connect(*server.sockets[0].getsockname())
        client.proto.send_gpgnet_message('Authenticate', ['42', '1'])
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
