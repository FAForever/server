from asyncio import coroutine, sleep
import asyncio
from concurrent.futures import CancelledError
import json
import time

from PySide.QtNetwork import QHostAddress
from mock import call
import pytest

from src.FaGamesServer import FAServer
from .testclient import TestGPGClient
import config


@coroutine
def wait_call(mock, call, timeout=0.5):
    start_time = time.time()
    yield from asyncio.sleep(0.1)
    while time.time() - start_time < timeout:
        if call in mock.mock_calls:
            return True
        yield from sleep(0.1)
    assert call in mock.mock_calls

@coroutine
def run_server(address, loop, player_service, games):
    with FAServer(loop, player_service, games, []) as server:
        if not server.run(QHostAddress(address)):
            pytest.fail('Failure running FAServer')
        yield from asyncio.wait_for(server.done, 2)

@asyncio.coroutine
def test_public_host(loop, qtbot, players, player_service, games):
    player = players.hosting
    server = asyncio.async(run_server('127.0.0.1', loop, player_service, games))
    yield from asyncio.sleep(0.1)
    with TestGPGClient('127.0.0.1', 8000, player.getGamePort(), process_nat_packets=True) as client:
        with qtbot.waitSignal(client.connected):
            pass
        client.send_GameState(['Idle'])
        client.send_GameState(['Lobby'])
        yield from wait_call(client.udp_messages,
                              call("\x08Are you public? %s" % player.id), 2)
        client.send_ProcessNatPacket(["%s:%s" % (player.getIp(), player.getGamePort()),
                                      "Are you public? %s" % player.id])
        yield from wait_call(client.messages,
                    call(json.dumps({"key": "ConnectivityState",
                    "commands": [player.id, "PUBLIC"]})), 2)
    server.cancel()


@asyncio.coroutine
def test_stun_host(loop, qtbot, players, player_service, games):
    player = players.hosting
    server = asyncio.async(run_server('127.0.0.1', loop, player_service, games))
    yield from asyncio.sleep(0.1)
    with TestGPGClient('127.0.0.1', 8000, player.getGamePort(), process_nat_packets=False) as client:
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
    server.cancel()
