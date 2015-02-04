from PySide.QtCore import Signal, QObject
from PySide.QtNetwork import QTcpSocket, QHostAddress
from JsonTransport import QDataStreamJsonTransport

import mock
import logging


class TestGPGClient(QObject):
    connected = Signal()

    def __init__(self, address, port, parent=None):
        super(TestGPGClient, self).__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Connecting to %s : %s" % (address, port))
        self.messages = mock.MagicMock()
        self.socket = QTcpSocket()
        self.socket.connected.connect(self._on_connected)
        self.socket.error.connect(self._on_error)
        self.socket.stateChanged.connect(self._on_state_change)
        self.transport = QDataStreamJsonTransport(self.socket)
        self.transport.messageReceived.connect(self.messages)
        self.socket.connectToHost(address, port)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.socket.abort()

    def _on_connected(self):
        self.logger.debug("Connected")
        self.connected.emit()

    def _on_error(self, msg):
        self.logger.info("Error %s" % msg)
        self.logger.info(self.socket.errorString())

    def _on_state_change(self, state):
        self.logger.debug("State changed to %s" % state)

    def sendGameState(self, arguments):
        self.transport.send_message({'action': 'GameState', 'chuncks': arguments})