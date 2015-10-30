import asyncio
import socket
from typing import Union
from unittest import mock

from typing import List
from unittest.mock import call

from server.decorators import with_logger
from server.protocol import QDataStreamProtocol
from server.protocol.gpgnet import GpgNetClientProtocol


@with_logger
class GpgClientProtocol:
    def __init__(self, receiver, reader, writer):
        super().__init__()
        self.receiver = receiver
        self.reader = reader
        self.writer = writer
        self.protocol = QDataStreamProtocol(reader, writer)

    @asyncio.coroutine
    def read_message(self):
        try:
            msg = yield from self.protocol.read_message()
            self.on_message_received(msg)
            return msg
        except Exception as ex:
            self._logger.exception(ex)
            self.writer.close()
            raise

    def write_eof(self):
        self.writer.write_eof()

    def close(self):
        self.writer.close()

    def on_message_received(self, message):
        self.receiver.on_message_received(message)

    def send_gpgnet_message(self, command_id, arguments):
        self.protocol.send_message({'action': command_id, 'chunks': arguments})


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
class TestGPGClient(GpgNetClientProtocol):
    """
    Client used for acting as a GPGNet client (The game itself).

    This means communicating with the GameServer
    through the GpgClientProtocol, and being able to
    send/receive out-of-band UDP messages.
    """
    def __init__(self, loop, process_nat_packets=True):
        super(TestGPGClient, self).__init__()
        self.process_nat_packets = process_nat_packets
        self.messages = mock.MagicMock()
        self.udp_messages = mock.MagicMock()
        self.loop = loop

        self._gpg_proto = None
        self._udp_transport, self._udp_protocol = (None, None)
        self._gpg_socket_pair = None

    def send_gpgnet_message(self, command_id, arguments: List[Union[int, str, bool]]) -> None:
        self._gpg_proto.protocol.send_message({'action': command_id, 'chunks': arguments})

    @asyncio.coroutine
    def connect(self, host, port, udp_port):
        self._logger.debug("Listening on 127.0.0.1:6112/udp, endpoint is %s:%s/udp" % (host, udp_port))
        self._udp_transport, self._udp_protocol =\
            yield from self.loop.create_datagram_endpoint(lambda: UDPClientProtocol(self.on_received_udp),
                                                          local_addr=('127.0.0.1', 6112))
        self._logger.debug("Connecting to %s:%s/tcp" % (host, port))
        self._gpg_socket_pair = yield from asyncio.open_connection(host, port)
        self._gpg_proto = GpgClientProtocol(self, *self._gpg_socket_pair)

    @asyncio.coroutine
    def read_until(self, value=None):
        while True:
            msg = yield from self._gpg_proto.read_message()
            if 'key' in msg and msg['key'] == value:
                return

    @asyncio.coroutine
    def read_until_eof(self):
        try:
            while True:
                yield from self._gpg_proto.read_message()
        except Exception as ex:
            self._logger.debug(ex)

    def received_udp_from(self, message, addr):
        return call(message, addr) in self.udp_messages.mock_calls

    def on_message_received(self, message):
        self.messages(message)

    def on_received_udp(self, msg, addr):
        self.udp_messages(msg, addr)
        if self.process_nat_packets:
            self._gpg_proto.send_gpgnet_message('ProcessNatPacket', ["{}:{}".format(*addr), msg])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._gpg_proto:
            self._gpg_proto.close()
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

    def send_pong(self):
        self.transport.send_message({'action': 'pong', 'chunks': []})
