from PySide.QtNetwork import QUdpSocket
import asyncio
import logging

logger = logging.getLogger(__name__)

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

    Three levels are defined:
        - PUBLIC:
             The peer is publicly accessible without prior communication
        - STUN:
             The peer must first send an outbound packet
             before being able to receive on the inbound port
        - PROXY:
             The peer is unable to connect by other means than proxy
    """
    def __int__(self):
        pass
