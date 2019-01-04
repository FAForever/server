import asyncio
from typing import Union
from unittest import mock

from typing import List
from unittest.mock import call

from server.decorators import with_logger
from server.protocol.gpgnet import GpgNetClientProtocol


@with_logger
class UDPClientProtocol:
    def __init__(self, on_message):
        self.transport = None
        self.on_message = on_message

    def connection_made(self, transport: asyncio.DatagramProtocol):
        print("UDPClientProtocol listening")
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        self.on_message(data.decode(), addr)

    def connection_lost(self, exc):
        print(exc)

    def send_datagram(self, msg: str):
        self.transport.sendto(msg.encode())

    def sendto(self, msg: str, addr):
        self.transport.sendto(msg.encode(), addr)


@with_logger
class ClientTest(GpgNetClientProtocol):
    """
    Client used for acting as a GPGNet client (The game itself).

    This means communicating with the GameServer
    through the GpgClientProtocol, and being able to
    send/receive out-of-band UDP messages.
    """
    def __init__(self, loop, process_nat_packets=True, proto=None):
        super(ClientTest, self).__init__()
        self.process_nat_packets = process_nat_packets
        self.messages = mock.MagicMock()
        self.udp_messages = mock.MagicMock()
        self.loop = loop

        self._proto = proto
        self._udp_transport, self._udp_protocol = (None, None)
        self._gpg_socket_pair = None

    def send_gpgnet_message(self, command_id, arguments: List[Union[int, str, bool]]) -> None:
        self._proto.send_message({'command': command_id,
                                  'target': 'game',
                                  'args': arguments})

    async def listen_udp(self, port=6112):
        self._logger.debug("Listening on 0.0.0.0:{}/udp".format(port))
        self._udp_transport, self._udp_protocol = \
            await self.loop.create_datagram_endpoint(lambda: UDPClientProtocol(self.on_received_udp),
                                                          local_addr=('0.0.0.0', port))

    @asyncio.coroutine
    def connect(self, host, port):
        self._logger.debug("Connecting to %s:%s/tcp" % (host, port))
        self._gpg_socket_pair = yield from asyncio.open_connection(host, port)

    @asyncio.coroutine
    def read_until(self, value=None):
        while True:
            msg = yield from self._proto.read_message()
            self.messages(msg)
            if 'command' in msg and msg['command'] == value:
                return

    def received_udp_from(self, message, addr):
        return call(message, addr) in self.udp_messages.mock_calls

    def on_received_udp(self, msg, addr):
        self._logger.debug("UDP({})<<: {}".format(addr, msg))
        # strip the \x08 byte from NAT packets
        msg = msg[1:]
        self.udp_messages(msg, addr)
        if self.process_nat_packets:
            self.send_gpgnet_message('ProcessNatPacket', ["{}:{}".format(*addr), msg])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._proto:
            self._proto.close()
        if self._udp_protocol:
            self._udp_protocol.transport.close()

    def _on_connected(self):
        self._logger.debug("Connected")

    def _on_error(self, msg):
        self._logger.critical("Error %s" % msg)
        self._logger.critical(self.tcp_socket.errorString())

    def _on_state_change(self, state):
        self._logger.debug("State changed to %s" % state)

    def send_udp_natpacket(self, msg, host, port):
        self._logger.debug("Sending UDP: {}:{}>>{}".format(host, port, msg))
        self._udp_protocol.sendto('\x08'+msg, (host, port))
