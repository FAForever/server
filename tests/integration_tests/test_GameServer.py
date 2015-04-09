from asyncio import coroutine, sleep
import asyncio
from concurrent.futures import CancelledError
import json
import time

from PySide.QtNetwork import QHostAddress
from mock import call
import pytest
from server.natpacketserver import NatPacketServer
from server.gameconnection import GameConnection

from tests.integration_tests.testclient import TestGPGClient
import config

slow = pytest.mark.slow

@coroutine
def wait_call(mock, call, timeout=0.5):
    start_time = time.time()
    yield from asyncio.sleep(0.1)
    while time.time() - start_time < timeout:
        if call in mock.mock_calls:
            return True
        yield from sleep(0.1)
    assert call in mock.mock_calls

def run_server(loop, player_service, games, db):
    nat_packet_server = NatPacketServer(loop, config.LOBBY_UDP_PORT)
    def initialize_connection():
        gc = GameConnection(loop, player_service, games, db)
        nat_packet_server.subscribe(gc, ['ProcessServerNatPacket'])
        return gc
    return nat_packet_server, loop.create_server(initialize_connection,
                                  '127.0.0.1', 8000)

@asyncio.coroutine
@slow
def test_public_host(loop, qtbot, players, player_service, games, db):
    player = players.hosting
    nat_server, server = run_server(loop, player_service, games, db)
    server = yield from server
    with TestGPGClient('127.0.0.1', 8000, player.gamePort, process_nat_packets=True) as client:
        with qtbot.waitSignal(client.connected):
            pass
        client.send_GameState(['Idle'])
        client.send_GameState(['Lobby'])
        yield from wait_call(client.udp_messages,
                              call("\x08Are you public? %s" % player.id), 2)
        client.send_ProcessNatPacket(["%s:%s" % (player.getIp(), player.gamePort),
                                      "Are you public? %s" % player.id])
        yield from wait_call(client.messages,
                    call(json.dumps({"key": "ConnectivityState",
                    "commands": [player.id, "PUBLIC"]})), 2)
    server.close()
    nat_server.close()
    yield from server.wait_closed()


@asyncio.coroutine
@slow
def test_stun_host(loop, qtbot, players, player_service, games, db):
    player = players.hosting
    nat_server, server = run_server(loop, player_service, games, db)
    server = yield from server
    with TestGPGClient('127.0.0.1', 8000, player.gamePort, process_nat_packets=False) as client:
        with qtbot.waitSignal(client.connected):
            pass
        client.send_GameState(['Idle'])
        client.send_GameState(['Lobby'])
        yield from wait_call(client.messages,
                      call(json.dumps({"key": "SendNatPacket",
                            "commands": ["%s:%s" % (config.LOBBY_IP, config.LOBBY_UDP_PORT),
                                         "Hello %s" % player.id]})), 2)

        client.send_udp_natpacket('Hello {}'.format(player.id), '127.0.0.1', config.LOBBY_UDP_PORT)

        yield from wait_call(client.messages,
                      call(json.dumps({"key": "ConnectivityState",
                                       "commands": [player.id, "STUN"]})), 2)
    server.close()
    nat_server.close()
    yield from server.wait_closed()
