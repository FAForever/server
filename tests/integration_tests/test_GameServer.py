from PySide.QtNetwork import QHostAddress
from PySide.QtCore import QCoreApplication
import mock
from FaGamesServer import FAServer
from .TestGPGClient import TestGPGClient
from tests.unit_tests.test_GameConnection import *
import logging
from players import playersOnline

logging.getLogger().addHandler(logging.StreamHandler())
logging.getLogger().setLevel(logging.DEBUG)
app = QCoreApplication([])
@pytest.fixture
def patch_config(monkeypatch):
    monkeypatch.setattr('GameConnection.config',
                        mock.MagicMock(spec={'global':
                             mock.MagicMock(return_value={'lobby_ip': '192.168.0.1'})}))

def test_timeout(qtbot, patch_config, player_service, games):
    with FAServer(player_service, games, [], []) as server:
        address = QHostAddress.SpecialAddress.LocalHost
        server.listen(address)
        with TestGPGClient(address, server.serverPort()) as client:
            with qtbot.waitSignal(client.transport.messageReceived):
                client.sendGameState(['Idle'])
                print(client.messages.mock_calls)
                assert False
