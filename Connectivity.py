from PySide.QtNetwork import QUdpSocket, QHostAddress
import asyncio
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class Observable():
    def __init__(self):
        pass
    def __call__(self, *args, **kwargs):
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

    def send_payload(self):
        logger.debug("UDP(%s:%s)>> %s" % (self.remote_addr, self.remote_port, self.message))
        self.socket.writeDatagram(self.message.encode(), self.remote_addr, self.remote_port)
        self.socket.abort()

    def _on_error(self):
        logger.debug("UDP socket error %s" % self.socket.errorString)


class TestPeer():
    """
    Determine the connectivity state of a peer.
    """
    def __init__(self, game_connection: Observable):
        """
        :param game_connection: Used for subscribing to ProcessNatPacket events
        :return: None
        """
        super(TestPeer, self).__init__()
        self.game_connection = game_connection

    def __enter__(self):
        self.game_connection.subscribe(self.handle_messsage)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.game_connection.unsubscribe(self.handle_messsage)

    def handle_message(self, message):
        pass

    @asyncio.coroutine
    def determine_connectivity(self):
        connectivity = Connectivity.PROXY
        public = yield from asyncio.wait_for(self.test_public(), 1)
        if public:
            connectivity = Connectivity.PUBLIC
        return connectivity

    @asyncio.coroutine
    def receive_nat_packet(self, message: str):
        pass

    @asyncio.coroutine
    def test_public(self):
        times_sent = 0
        while times_sent < 3:
            self.game_connection.log.debug("Sending connectivity packet")
            UdpMessage(QHostAddress(self.game_connection.player.getIp()),
                       self.game_connection.player.getGamePort(),
                       '\x08ARE YOU ALIVE? %s' % self.game_connection.player.getId())
            yield from asyncio.sleep(0.1)
            if self.game_connection.connectivity_state == 'PUBLIC':
                return Connectivity.PUBLIC
            times_sent += 1
        return Connectivity.STUN
