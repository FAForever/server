from asyncio import TimeoutError
import json

from PySide.QtNetwork import QHostAddress
from FaGamesServer import FAServer
from .TestGPGClient import TestGPGClient
from ..utils import wait_signal

def test_out_of_band_udp(loop, patch_config, players, player_service, games):
    player = players.hosting
    with FAServer(loop, player_service, games, [], []) as server:
        address = QHostAddress.SpecialAddress.LocalHost
        server.listen(address)
        with TestGPGClient(address, server.serverPort(), 6112) as client:
            client.send_game_state(['Idle'])
            client.send_game_state(['Lobby'])
            loop.run_until_complete(wait_signal(client.receivedUdp, 2))
            client.udp_messages.assert_any_call("\x08Are you public? %s" % player.getId())
            client.send_process_nat_packet(["%s:%s" % (player.getIp(), player.getGamePort()),
                                            "Are you public? %s" % player.getId()])
            loop.run_until_complete(wait_signal(client.receivedTcp, 2))
            client.messages.assert_any_call(json.dumps({"key": "ConnectivityState",
                                                        "commands": [player.getId(), "PUBLIC"]}))
            try:
                # Give remaining processing a chance to shut down before closing the event loop
                # This will go away as more stuff is moved to asyncio
                loop.run_until_complete(wait_signal(client.receivedTcp, 0.5))
            except TimeoutError:
                pass
