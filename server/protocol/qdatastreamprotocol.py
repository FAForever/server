import asyncio

import json
import struct
import base64
from asyncio import StreamReader, StreamWriter

import server
from server.decorators import with_logger
from .protocol import Protocol


@with_logger
class QDataStreamProtocol(Protocol):
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
            raise ValueError("Malformed QString: Claims length {} but actually {}. Entire buffer: {}"
                             .format(size, len(buffer[pos + 4:]), base64.b64encode(buffer)))
        return size + pos + 4, (buffer[pos + 4:pos + 4 + size]).decode('UTF-16BE')

    @staticmethod
    def read_int32(buffer, pos=0):
        """
        Read a serialized 32-bit integer from the given buffer at given position

        :type buffer: bytes
        :return (int, int): (buffer_pos, int)
        """
        assert len(buffer[pos:pos + 4]) == 4
        (num, ) = struct.unpack('!i', buffer[pos:pos + 4])
        return pos + 4, num

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
        if action in ['UPLOAD_MAP', 'UPLOAD_MOD']:
            pos, _ = self.read_qstring(block, pos)  # login
            pos, _ = self.read_qstring(block, pos)  # session
            pos, name = self.read_qstring(block, pos)
            pos, info = self.read_qstring(block, pos)
            pos, size = self.read_int32(block, pos)
            data = block[pos:size]
            return {
                'command': action.lower(),
                'name': name,
                'info': json.loads(info),
                'data': data
            }
        elif action in ['PING', 'PONG']:
            return {
                'command': action.lower()
            }
        else:
            message = json.loads(action)
            for part in self.read_block(block):
                try:
                    message_part = json.loads(part)
                    message.update(message_part)
                except (ValueError, TypeError):
                    if 'legacy' not in message:
                        message['legacy'] = []
                    message['legacy'].append(part)
            return message

    async def drain(self):
        """
        Await the write buffer to empty.

        See StreamWriter.drain()
        """
        await asyncio.sleep(0)
        await self.writer.drain()

    def close(self):
        """
        Close writer stream
        :return:
        """
        self.writer.close()

    def send_message(self, message: dict):
        self.writer.write(self.pack_message(json.dumps(message)))
        server.stats.incr('server.sent_messages')

    def send_messages(self, messages):
        server.stats.incr('server.sent_messages')
        payload = [self.pack_message(json.dumps(msg)) for msg in messages]
        self.writer.writelines(payload)

    def send_raw(self, data):
        server.stats.incr('server.sent_messages')
        self.writer.write(data)
