from PySide.QtNetwork import QHostAddress

from FaGamesServer import FAServer
from .TestGPGClient import TestGPGClient
from tests.unit_tests.test_GameConnection import *
import json
import asyncio


@pytest.fixture
def patch_config(monkeypatch):
    monkeypatch.setattr('GameConnection.config',
                        mock.MagicMock(spec={'global':
                             mock.MagicMock(return_value={'lobby_ip': '192.168.0.1'})}))

@asyncio.coroutine
def wait_signal(signal, timeout=0.5):
    future = asyncio.Future()
    def fire():
        future.set_result(True)
    signal.connect(fire)
    yield from asyncio.wait_for(future, timeout)

def test_out_of_band_udp(loop, patch_config, players, player_service, games):
    player = players.hosting
    with FAServer(loop, player_service, games, [], []) as server:
        address = QHostAddress.SpecialAddress.LocalHost
        server.listen(address)
        with TestGPGClient(address, server.serverPort(), 6112) as client:
            client.send_game_state(['Idle'])
            client.send_game_state(['Lobby'])
            loop.run_until_complete(wait_signal(client.receivedUdp, 2))
            client.udp_messages.assert_any_call("\x08ARE YOU ALIVE? %s" % player.getId())
            client.send_process_nat_packet(["%s:%s" % (player.getIp(), player.getGamePort()),
                                            "ARE YOU ALIVE? %s" % player.getId()])
            loop.run_until_complete(wait_signal(client.receivedTcp, 2))
            print(client.messages.mock_calls)
            client.messages.assert_any_call(json.dumps({"key": "ConnectivityState", "commands": [player.getId(), "PUBLIC"]}))
