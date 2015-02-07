from concurrent.futures import CancelledError, TimeoutError
from PySide.QtNetwork import QUdpSocket, QHostAddress
import asyncio
import logging
from enum import Enum

from config import config

logger = logging.getLogger(__name__)


class Observable():
    def __init__(self):
        pass

    def subscribe(self):
        pass

    def unsubscribe(self):
        pass


class Connectivity(Enum):
    """
    Describes the connectivity level of a peer
    Three levels are defined:
        - PUBLIC:
        The peer is publicly accessible without prior communication
        - STUN:
            The peer must first send an outbound packet
            before being able to receive on the inbound port
        - PROXY:
            The peer is unable to connect by other means than proxy
    """
    PUBLIC = "PUBLIC"
    STUN = "STUN"
    PROXY = "PROXY"


class UdpMessage():
    def __init__(self, remote_addr, remote_port, message):
        self.message = message
        self.remote_addr = remote_addr
        self.remote_port = remote_port
        self.socket = QUdpSocket()
        self.socket.connected.connect(self.send_payload)
        self.socket.connectToHost(remote_addr, remote_port)
        self.socket.error.connect(self._on_error)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.socket.abort()
        except:
            pass

    def send_payload(self):
        logger.debug("UDP(%s:%s)>> %s" % (self.remote_addr.toString(), self.remote_port, self.message))
        self.socket.writeDatagram(self.message.encode(), self.remote_addr, self.remote_port)

    def _on_error(self):
        logger.debug("UDP socket error %s" % self.socket.errorString)


class TestPeer():
    """
    Determine the connectivity state of a peer.
    """

    def __init__(self, connection,
                 host: str,
                 port: int,
                 identifier: str):
        """
        :param events: Used for subscribing to ProcessNatPacket events
        :return: None
        """
        super(TestPeer, self).__init__()
        self.connection = connection
        self.connectivity_state = None
        self.remote_addr = (host, port)
        self.identifier = identifier
        self.connection.log.debug("Testing peer connectivity")
        self.packets = []

    def __enter__(self):
        self.connection.subscribe(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.connection.unsubscribe(self)


    @asyncio.coroutine
    def determine_connectivity(self):
        try:
            if (yield from self.test_public()):
                return Connectivity.PUBLIC
            elif (yield from self.test_stun()):
                return Connectivity.STUN
            else:
                return Connectivity.PROXY
        except (TimeoutError, CancelledError):
            pass
        return Connectivity.PROXY

    def handle_ProcessNatPacket(self, arguments):
        self.packets.append(arguments)

    @asyncio.coroutine
    def test_public(self):
        for i in range(1, 3):
            with UdpMessage(QHostAddress(self.remote_addr[0]),
                            self.remote_addr[1],
                            "\x08Are you public? %s" % self.identifier):
                yield from asyncio.sleep(0.1)
        return any(map(lambda args: "Are you public? %s" % self.identifier in args,
                       self.packets))

    @asyncio.coroutine
    def test_stun(self):
        try:
            self.connection.sendToRelay('SendNatPacket', ["%s:%s" % (config['lobby_ip'],
                                                                     config['lobby_udptest_port']),
                                                          "Hello %s" % self.identifier])
            yield from asyncio.sleep(0.1)
        except CancelledError:
            pass
