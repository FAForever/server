from abc import ABCMeta, abstractmethod
import struct
import asyncio
from server.decorators import with_logger

@with_logger
class BaseStatefulProtocol(asyncio.Protocol, metaclass=ABCMeta):
    connections = []

    def __init__(self):
        super().__init__()
        self._transport = None
        self._logger.info("Stateful protocol initialized")

    def connection_made(self, transport):
        self._logger.info("Connection Made")
        self._transport = transport
        self.connections.append(self)
        try:
            self.on_connection_made(transport.get_extra_info('peername'))
        except Exception as ex:
            self._logger.warning("Error during on_connection_made")
            self._logger.exception(ex)

    def connection_lost(self, exc):
        self.connections.remove(self)
        try:
            self.on_connection_lost(exc)
        except Exception as ex:
            self._logger.warning("Error during on_connection_lost")
            self._logger.exception(ex)

    def on_message_received(self, message):
        pass  # pragma: no cover

    def on_connection_made(self, peername):
        pass  # pragma: no cover

    def on_connection_lost(self, exc):
        pass  # pragma: no cover


@with_logger
class QDataStreamProtocol(BaseStatefulProtocol):
    """
    Base class for implementing the legacy QDataStream-based encoding scheme
    """
    @staticmethod
    def read_qstring(message):
        """
        Parse a serialized QString from message

        Requires len(message) > 4
        :type message: bytes
        :return: (message_size, message)
        """
        (message_size, ) = struct.unpack('!I', message[:4])
        if len(message[4:]) < message_size:
            raise ValueError("Malformed QString: Claims length {} but actually {}"
                             .format(len(message[4:]), message_size))
        return message_size, (message[4:4 + message_size]).decode('UTF-16BE')

    @staticmethod
    def pack_qstring(message):
        encoded = message.encode('UTF-16BE')
        return struct.pack('!i', len(encoded)) + encoded

    @staticmethod
    def pack_block(block):
        return struct.pack('!I', len(block)) + block

    @staticmethod
    def read_blocks(data):
        while len(data) >= 4:
            (length, ) = struct.unpack('!I', data[:4])
            message = data[4:4 + length]
            while len(message) > 0:
                str_length, msg = QDataStreamProtocol.read_qstring(message)
                message = message[4 + str_length:]
                yield msg
            data = data[4 + length:]

    def data_received(self, data):
        try:
            print(len(data))
            for msg in self.read_blocks(data):
                self.on_message_received(msg)
        except Exception as ex:
            self._logger.warning("Error during on_message_received")
            self._logger.exception(ex)
            self._transport.write_eof()

    def send_legacy(self, message, *args):
        """
        For sending a bunch of QStrings packed together in a 'block'
        """
        msg = self.pack_qstring(message)
        for arg in args:
            if isinstance(arg, str):
                msg += self.pack_qstring(arg)
            else:
                raise NotImplementedError("Only string serialization is supported")
        self._transport.write(self.pack_block(msg))

    def send_message(self, message):
        self._transport.write(self.pack_block(self.pack_qstring(message)))

    def send_messages(self, messages):
        payload = [self.pack_block(self.pack_qstring(msg)) for msg in messages]
        self._transport.writelines(payload)
