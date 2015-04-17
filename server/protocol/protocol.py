from abc import ABCMeta
from asyncio import StreamReader, StreamWriter
import asyncio
import struct
import ujson
from server.decorators import with_logger

@with_logger
class QDataStreamProtocol(metaclass=ABCMeta):
    """
    Implements the legacy QDataStream-based encoding scheme
    """
    def __init__(self, reader: StreamReader, writer: StreamWriter):
        """
        Initialize the protocol

        :param StreamReader reader: asyncio stream to read from
        """
        self.reader = reader
        self.writer = writer

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
                             .format(message_size, len(message[4:])))
        return message_size, (message[4:4 + message_size]).decode('UTF-16BE')

    @staticmethod
    def pack_qstring(message):
        encoded = message.encode('UTF-16BE')
        return struct.pack('!i', len(encoded)) + encoded

    @staticmethod
    def pack_block(block):
        return struct.pack('!I', len(block)) + block

    @staticmethod
    def read_block(data):
        while len(data) > 0:
            str_length, msg = QDataStreamProtocol.read_qstring(data)
            data = data[4 + str_length:]
            yield msg


    @staticmethod
    def read_blocks(data):
        while len(data) >= 4:
            (length, ) = struct.unpack('!I', data[:4])
            message = data[4:4 + length]
            yield QDataStreamProtocol.read_block(message)
            data = data[4 + length:]

    @staticmethod
    def pack_message(message, *args):
        """
        For sending a bunch of QStrings packed together in a 'block'
        """
        msg = QDataStreamProtocol.pack_qstring(message)
        for arg in args:
            if isinstance(arg, str):
                msg += QDataStreamProtocol.pack_qstring(arg)
            else:
                raise NotImplementedError("Only string serialization is supported")
        return QDataStreamProtocol.pack_block(msg)

    @asyncio.coroutine
    def read_message(self):
        """
        Read a message from the stream

        On malformed stream, raises IncompleteReadError
        """
        (block_length, ) = struct.unpack('!I', (yield from self.reader.readexactly(4)))
        block = yield from self.reader.readexactly(block_length)
        # FIXME: New protocol will remove the need for this
        message = {'legacy': []}
        for part in self.read_block(block):
            try:
                message_part = ujson.loads(part)
                message.update(message_part)
            except (ValueError, TypeError):
                message['legacy'].append(part)
        return message

    def send_message(self, message: dict):
        self.writer.write(self.pack_message(ujson.dumps(message)))

    def send_messages(self, messages):
        payload = [self.pack_block(self.pack_qstring(msg)) for msg in messages]
        self.writer.writelines(payload)
