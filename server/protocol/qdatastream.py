import base64
import json
import struct
from typing import Tuple

from server.decorators import with_logger

from .protocol import Protocol

json_encoder = json.JSONEncoder(separators=(',', ':'))


@with_logger
class QDataStreamProtocol(Protocol):
    """
    Implements the legacy QDataStream-based encoding scheme
    """

    @staticmethod
    def read_qstring(buffer: bytes, pos: int = 0) -> Tuple[int, str]:
        """
        Parse a serialized QString from buffer (A bytes like object) at given position

        Requires len(buffer[pos:]) >= 4.

        Pos is added to buffer_pos.

        :type buffer: bytes
        :return (int, str): (buffer_pos, message)
        """
        chunk = buffer[pos:pos + 4]
        rest = buffer[pos + 4:]
        assert len(chunk) == 4

        (size, ) = struct.unpack('!I', chunk)
        if len(rest) < size:
            raise ValueError(
                "Malformed QString: Claims length {} but actually {}. Entire buffer: {}"
                .format(size, len(rest), base64.b64encode(buffer)))
        return size + pos + 4, (buffer[pos + 4:pos + 4 + size]).decode('UTF-16BE')

    @staticmethod
    def pack_qstring(message: str) -> bytes:
        encoded = message.encode('UTF-16BE')
        return struct.pack('!i', len(encoded)) + encoded

    @staticmethod
    def pack_block(block: bytes) -> bytes:
        return struct.pack('!I', len(block)) + block

    @staticmethod
    def read_block(data):
        buffer_pos = 0
        while len(data[buffer_pos:]) > 4:
            buffer_pos, msg = QDataStreamProtocol.read_qstring(data, buffer_pos)
            yield msg

    @staticmethod
    def pack_message(*args: str) -> bytes:
        """
        For sending a bunch of QStrings packed together in a 'block'
        """
        msg = bytearray()
        for arg in args:
            if not isinstance(arg, str):
                raise NotImplementedError("Only string serialization is supported")

            msg += QDataStreamProtocol.pack_qstring(arg)
        return QDataStreamProtocol.pack_block(msg)

    @staticmethod
    def encode_message(message: dict) -> bytes:
        """
        Encodes a python object as a block of QStrings
        """
        command = message.get("command")
        if command == "ping":
            return PING_MSG
        elif command == "pong":
            return PONG_MSG

        return QDataStreamProtocol.pack_message(json_encoder.encode(message))

    async def read_message(self):
        """
        Read a message from the stream

        On malformed stream, raises IncompleteReadError

        :return dict: Parsed message
        """
        (block_length, ) = struct.unpack('!I', (await self.reader.readexactly(4)))
        block = await self.reader.readexactly(block_length)
        # FIXME: New protocol will remove the need for this

        pos, action = self.read_qstring(block)
        if action in ['PING', 'PONG']:
            return {'command': action.lower()}
        else:
            message = json.loads(action)
            try:
                for part in self.read_block(block):
                    try:
                        message_part = json.loads(part)
                        if part != action:
                            message.update(message_part)
                    except (ValueError, TypeError):
                        if 'legacy' not in message:
                            message['legacy'] = []
                        message['legacy'].append(part)
            except (KeyError, ValueError):
                pass
            return message


PING_MSG = QDataStreamProtocol.pack_message("PING")
PONG_MSG = QDataStreamProtocol.pack_message("PONG")
