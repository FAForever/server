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
    def read_qstring(buffer, pos=0):
        """
        Parse a serialized QString from buffer (A bytes like object) at given position

        Requires len(buffer[pos:]) >= 4.

        Pos is added to buffer_pos.

        :type buffer: bytes
        :return (int, str): (buffer_pos, message)
        """
        assert len(buffer[pos:pos + 4]) == 4
        (size, ) = struct.unpack('!I', buffer[pos:pos + 4])
        if len(buffer[pos + 4:]) < size:
            raise ValueError("Malformed QString: Claims length {} but actually {}"
                             .format(size, len(buffer[pos + 4:])))
        return size + pos + 4, (buffer[pos + 4:pos + 4 + size]).decode('UTF-16BE')

    @staticmethod
    def pack_qstring(message):
        encoded = message.encode('UTF-16BE')
        return struct.pack('!i', len(encoded)) + encoded

    @staticmethod
    def pack_block(block):
        return struct.pack('!I', len(block)) + block

    @staticmethod
    def read_block(data):
        buffer_pos = 0
        while len(data[buffer_pos:]) > 4:
            buffer_pos, msg = QDataStreamProtocol.read_qstring(data, buffer_pos)
            yield msg

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

        :return dict: Parsed message
        """
        (block_length, ) = struct.unpack('!I', (yield from self.reader.readexactly(4)))
        block = yield from self.reader.readexactly(block_length)
        # FIXME: New protocol will remove the need for this

        pos, action = self.read_qstring(block)
        if action == 'CREATE_ACCOUNT':
            pos, login = self.read_qstring(block, pos)
            pos, email = self.read_qstring(block, pos)
            pos, password = self.read_qstring(block, pos)
            return {
                'command': "create_account",
                'login': login,
                'email': email,
                'password': password
            }
        elif action in ['UPLOAD_MAP', 'UPLOAD_MOD']:
            pos, _ = self.read_qstring(block, pos)  # login
            pos, _ = self.read_qstring(block, pos)  # session
            pos, name = self.read_qstring(block, pos)
            pos, info = self.read_qstring(block, pos)
            pos, size = self.read_int32(block, pos)
            data = block[pos:size]
            return {
                'command': 'command_{}'.format(action.lower()),
                'name': name,
                'info': ujson.loads(info),
                'data': data
            }
        elif action in ['PING', 'PONG']:
            return {
                'command': 'command_{}'.format(action.lower())
            }
        else:
            message = ujson.loads(action)
            for part in self.read_block(block):
                try:
                    message_part = ujson.loads(part)
                    message.update(message_part)
                except (ValueError, TypeError):
                    if 'legacy' not in message:
                        message['legacy'] = []
                    message['legacy'].append(part)
            return message

    def send_message(self, message: dict):
        self.writer.write(self.pack_message(ujson.dumps(message)))

    def send_messages(self, messages):
        payload = [self.pack_block(self.pack_qstring(msg)) for msg in messages]
        self.writer.writelines(payload)

    @asyncio.coroutine
    def send_raw(self, data):
        self.writer.write(data)
        yield from self.writer.drain()
