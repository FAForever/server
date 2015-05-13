import asyncio
import socket

from PySide.QtCore import QObject
from PySide.QtNetwork import QUdpSocket
import mock
from server.decorators import with_logger
from server.protocol import QDataStreamProtocol
from server.protocol.gpgnet import GpgNetClientProtocol


@with_logger
class GpgClientProtocol(GpgNetClientProtocol):
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
        self.protocol.send_message({'action': command_id, 'chuncks': arguments})



@with_logger
class TestGPGClient(QObject):
    """
    Client used for acting as a GPGNet client.
    This means communicating with the GameServer
    through the GpgClientProtocol, and being able to
    send/receive out-of-band UDP messages.
    """
    def __init__(self, udp_port, loop, process_nat_packets=True, parent=None):
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
        self.process_nat_packets = process_nat_packets
        self._logger.debug("Listening for UDP on: %s" % udp_port)
        self.messages = mock.MagicMock()
        self.udp_messages = mock.MagicMock()
        self.loop = loop
        self.udp_socket = QUdpSocket()
        self.udp_socket.connected.connect(self._on_connected)
        self.udp_socket.error.connect(self._on_error)
        self.udp_socket.stateChanged.connect(self._on_state_change)
        self.udp_socket.readyRead.connect(self._on_udp_message)

        self.proto = None
        self.client_pair = None
        self.udp_socket.bind(udp_port)

    @asyncio.coroutine
    def connect(self, host, port):
        self._logger.debug("Connecting to %s: %s" % (host, port))
        self.client_pair = yield from asyncio.open_connection(host, port)
        self.proto = GpgClientProtocol(self, *self.client_pair)

    @asyncio.coroutine
    def read_until(self, value=None):
        while True:
            msg = yield from self.proto.read_message()
            if 'key' in msg and msg['key'] == value:
                return


    @asyncio.coroutine
    def read_until_eof(self):
        try:
            while True:
                yield from self.proto.read_message()
        except Exception as ex:
            self._logger.debug(ex)

    def on_message_received(self, message):
        self.messages(message)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.proto.close()
        self.udp_socket.abort()

    def _on_udp_message(self):
        try:
            while self.udp_socket.hasPendingDatagrams():
                data, host, port = self.udp_socket.readDatagram(self.udp_socket.pendingDatagramSize())
                self._logger.debug("UDP(%s:%s)<< %s" % (host.toString(), port, data.data()))
                if self.process_nat_packets and data.data()[0] == 0x08:
                    self.proto.send_ProcessNatPacket(["{}:{}".format(host.toString(), port),
                                                data.data()[1:].decode()])

                self.udp_messages(str(data))
        except Exception as ex:
            self._logger.critical('Exception')
            self._logger.exception(ex)
            raise

    def _on_connected(self):
        self._logger.debug("Connected")

    def _on_error(self, msg):
        self._logger.critical("Error %s" % msg)
        self._logger.critical(self.tcp_socket.errorString())

    def _on_state_change(self, state):
        self._logger.debug("State changed to %s" % state)

    def send_udp_natpacket(self, msg, host, port):
        self._logger.debug("Sending UDP: {}:{}>>{}".format(host, port, msg))
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((host, port))
        s.sendall('\x08{}'.format(msg).encode())
        s.close()

    def send_pong(self):
        self.transport.send_message({'action': 'pong', 'chuncks': []})
