from asyncio import coroutine, sleep, TimeoutError
import json

from PySide.QtNetwork import QHostAddress
from mock import call, patch
from FaGamesServer import FAServer
from .TestGPGClient import TestGPGClient
import config
from ..utils import wait_signal
import gameconnection

import time

@coroutine
def wait_call(mock, call, timeout=0.5):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if call in mock.mock_calls:
            return True
        yield from sleep(0.1)
    assert call in mock.mock_calls

def test_public_host(loop, players, player_service, games):
    player = players.hosting
    with FAServer(loop, player_service, games, [], []) as server:
        address = QHostAddress.SpecialAddress.LocalHost
        server.listen(address)
        with TestGPGClient(address, server.serverPort(), 6112) as client:
            client.send_game_state(['Idle'])
            client.send_game_state(['Lobby'])
            loop.run_until_complete(wait_call(client.udp_messages,
                                              call("\x08Are you public? %s" % player.getId())))
            client.send_process_nat_packet(["%s:%s" % (player.getIp(), player.getGamePort()),
                                            "Are you public? %s" % player.getId()])
            loop.run_until_complete(wait_call(client.messages,
                                              call(json.dumps({"key": "ConnectivityState",
                                                               "commands": [player.getId(), "PUBLIC"]}))))

def test_stun_host(loop, players, player_service, games):
    player = players.hosting
    with FAServer(loop, player_service, games, [], []) as server:
        address = QHostAddress.SpecialAddress.LocalHost
        server.listen(address)
        with TestGPGClient(address, server.serverPort(), 6112) as client:
            client.send_game_state(['Idle'])
            client.send_game_state(['Lobby'])
            loop.run_until_complete(wait_call(client.messages,
                                              call(json.dumps({"key": "SendNatPacket",
                                                    "commands": ["%s:%s" % (config.LOBBY_IP, config.LOBBY_UDP_PORT),
                                                                 "Hello %s" % player.getId()]})), 2))
