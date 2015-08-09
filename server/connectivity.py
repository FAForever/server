from collections import namedtuple
from concurrent.futures import CancelledError, TimeoutError
import asyncio
import logging
from enum import Enum
import socket

import config
from .decorators import with_logger


logger = logging.getLogger(__name__)


class ConnectivityState(Enum):
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

Connectivity = namedtuple('Connectivity', ['addr', 'state'])

def send_natpacket(addr, message):
    logger.debug("UDP(%s,%s)>>: %s" % (addr[0], addr[1], message))
    s = socket.socket(type=socket.SOCK_DGRAM)
    s.setblocking(False)
    s.sendto(b'\x08'+message.encode(), addr)
    s.close()

@with_logger
class TestPeer:
    """
    Determine the connectivity state of a single peer.
    """

    def __init__(self,
                 connection,
                 host: str,
                 port: int,
                 identifier: str):
        """
        :return: None
        """
        super(TestPeer, self).__init__()
        self.connection = connection
        self.connectivity_state = None
        self.remote_addr = (host, port)
        self.identifier = identifier
        self.connection.log.debug("Testing peer connectivity")
        self.client_packets = []
        self.server_packets = []

    def __enter__(self):
        self.connection.subscribe(self, ['ProcessNatPacket', 'ProcessServerNatPacket'])
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.connection.unsubscribe(self, ['ProcessNatPacket', 'ProcessServerNatPacket'])

    @asyncio.coroutine
    def determine_connectivity(self):
        """
        Determine connectivity of peer

        :return: Connectivity(addr, ConnectivityState)
        """
        try:
            if (yield from self.test_public()):
                return Connectivity(addr="{}:{}".format(*self.remote_addr), state=ConnectivityState.PUBLIC)
            addr = yield from self.test_stun()
            if addr:
                return Connectivity(addr=addr, state=ConnectivityState.STUN)
            else:
                return Connectivity(addr=None, state=ConnectivityState.PROXY)
        except (TimeoutError, CancelledError):
            pass
        return Connectivity(addr=None, state=ConnectivityState.PROXY)

    def handle_ProcessNatPacket(self, arguments):
        self._logger.debug("handle_ProcessNatPacket {}".format(arguments))
        self.client_packets.append(arguments)

    def handle_ProcessServerNatPacket(self, arguments):
        self._logger.debug("handle_ProcessServerNatPacket {}".format(arguments))
        self.server_packets.append(arguments)

    @asyncio.coroutine
    def test_public(self):
        self._logger.debug("Testing PUBLIC")
        self._logger.debug(self.client_packets)
        message = "Are you public? {}".format(self.identifier)
        for i in range(0, 3):
            send_natpacket(self.remote_addr, message)
            yield from asyncio.sleep(0.2)
        return any(map(lambda packets: message in packets, self.client_packets))

    def received_server_packet(self):
        for packet in self.server_packets:
            print(packet)
            if len(packet) >= 2 and packet[1] == "Hello {}".format(self.identifier):
                return packet[0]

    @asyncio.coroutine
    def test_stun(self):
        self._logger.debug("Testing STUN")
        for i in range(0, 3):
            self.connection.send_gpgnet_message('SendNatPacket', ["%s:%s" % (config.LOBBY_IP,
                                                                     config.LOBBY_UDP_PORT),
                                                          "Hello %s" % self.identifier])
            resolution = self.received_server_packet()
            if resolution:
                self._logger.info("Resolved client to {}".format(resolution))
                return resolution
            yield from asyncio.sleep(0.1)
        return self.received_server_packet()

