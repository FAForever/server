from asyncio import coroutine, sleep
import asyncio
from concurrent.futures import CancelledError
import json
import time

from PySide.QtNetwork import QHostAddress
from mock import call
import pytest

from FaGamesServer import FAServer
from .testclient import TestGPGClient
import config



@coroutine
def wait_call(mock, call, timeout=0.5):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if call in mock.mock_calls:
            return True
        yield from sleep(0.1)
    assert call in mock.mock_calls

@coroutine
def run_server(address, loop, player_service, games):
    try:
        with FAServer(loop, player_service, games, [], []) as server:
            server.run(QHostAddress(address))
            yield from asyncio.wait_for(server.done, 2)
            server.close()
    except (CancelledError, TimeoutError) as e:
        pass

@pytest.mark.skipif(True, reason='Run these slow tests manually as needed')
def test_public_host(loop, qtbot, players, player_service, games):
    @coroutine
    def test():
        player = players.hosting
        server = asyncio.async(run_server('127.0.0.1', loop, player_service, games))
        with TestGPGClient('127.0.0.1', 8000, player.getGamePort()) as client:
            with qtbot.waitSignal(client.connected):
                pass
            client.send_GameState(['Idle'])
            client.send_GameState(['Lobby'])
            yield from wait_call(client.udp_messages,
                                  call("\x08Are you public? %s" % player.getId()), 3)
            client.send_ProcessNatPacket(["%s:%s" % (player.getIp(), player.getGamePort()),
                                          "Are you public? %s" % player.getId()])
            yield from wait_call(client.messages,
                        call(json.dumps({"key": "ConnectivityState",
                        "commands": [player.getId(), "PUBLIC"]})), 2)
    loop.run_until_complete(asyncio.wait_for(test(), timeout=3))


@pytest.mark.skipif(True, reason='Run these slow tests manually as needed')
def test_stun_host(loop, qtbot, players, player_service, games):
    @asyncio.coroutine
    def test():
        player = players.hosting
        server = asyncio.async(run_server('127.0.0.1', loop, player_service, games))
        with TestGPGClient('127.0.0.1', 8000, player.getGamePort()) as client:
            with qtbot.waitSignal(client.connected):
                pass
            client.send_GameState(['Idle'])
            client.send_GameState(['Lobby'])
            yield from wait_call(client.messages,
                          call(json.dumps({"key": "SendNatPacket",
                                "commands": ["%s:%s" % (config.LOBBY_IP, config.LOBBY_UDP_PORT),
                                             "Hello %s" % player.getId()]})), 2)

            client.send_udp_natpacket('Hello 2', '127.0.0.1', config.LOBBY_UDP_PORT)

            yield from wait_call(client.messages,
                          call(json.dumps({"key": "ConnectivityState",
                                           "commands": [player.getId(), "STUN"]})), 2)
        server.cancel()
    loop.run_until_complete(asyncio.wait_for(test(), timeout=3))
