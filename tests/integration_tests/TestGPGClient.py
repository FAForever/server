from PySide.QtCore import Signal, QObject
from PySide.QtNetwork import QTcpSocket, QUdpSocket, QHostAddress
from JsonTransport import QDataStreamJsonTransport

import asyncio
import mock
import logging
import time


class TestGPGClient(QObject):
    connected = Signal()
    receivedTcp = Signal(str)
    receivedUdp = Signal(str)

    def __init__(self, address, port, udp_port, parent=None):
        """
        Initialize the test client
        :param loop: asyncio event loop:
            The event loop to use for listening on UDP
        :param address: QHostAddress:
            The address to connect to
        :param port: int:
            The port number to connect to
        :param udp_port:
        :param parent:
        :return:
        """
        super(TestGPGClient, self).__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Connecting to %s: %s" % (address, port))
        self.logger.debug("Listening for UDP on: %s" % udp_port)
        self.messages = mock.MagicMock()
        self.udp_messages = mock.MagicMock()
        self.tcp_socket = QTcpSocket()
        self.udp_socket = QUdpSocket()
        self.udp_socket.connected.connect(self._on_connected)
        self.udp_socket.error.connect(self._on_error)
        self.udp_socket.stateChanged.connect(self._on_state_change)
        self.udp_socket.readyRead.connect(self._on_udp_message)
        self.tcp_socket.connected.connect(self._on_connected)
        self.tcp_socket.error.connect(self._on_error)
        self.tcp_socket.stateChanged.connect(self._on_state_change)
        self.transport = QDataStreamJsonTransport(self.tcp_socket)
        self.transport.messageReceived.connect(self.messages)
        self.tcp_socket.connectToHost(address, port)
        self.udp_socket.bind(udp_port)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tcp_socket.abort()
        self.udp_socket.abort()

    def _on_udp_message(self):
        while self.udp_socket.hasPendingDatagrams():
            data, host, port = self.udp_socket.readDatagram(self.udp_socket.pendingDatagramSize())
            self.logger.debug("UDP(%s:%s)<< %s" % (host, port, data))
            self.udp_messages(str(data))
            self.receivedUdp.emit(data)

    def _on_connected(self):
        self.logger.debug("Connected")
        self.connected.emit()

    def _on_error(self, msg):
        self.logger.critical("Error %s" % msg)
        self.logger.critical(self.tcp_socket.errorString())

    def _on_state_change(self, state):
        self.logger.debug("State changed to %s" % state)

    def send_pong(self):
        self.transport.send_message({'action': 'pong', 'chuncks': []})

    def send_game_state(self, arguments):
        self.transport.send_message({'action': 'GameState', 'chuncks': arguments})