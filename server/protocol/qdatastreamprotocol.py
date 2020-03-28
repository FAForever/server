import asyncio
import base64
import contextlib
import json
import struct
from asyncio import StreamReader, StreamWriter
from typing import Tuple

import server.metrics as metrics
from server.decorators import with_logger

from .protocol import Protocol

json_encoder = json.JSONEncoder(separators=(',', ':'))


class DisconnectedError(ConnectionError):
    """For signaling that a protocol has lost connection to the remote."""


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
        # Force calls to drain() to only return once the data has been sent
        self.writer.transport.set_write_buffer_limits(high=0)

        # drain() cannot be called concurrently by multiple coroutines:
        # http://bugs.python.org/issue29930.
        self._drain_lock = asyncio.Lock()

    def is_connected(self) -> bool:
        return not self.writer.is_closing()

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
    def encode_message(message) -> bytes:
        """
        Encodes a python object as raw bytes
        """
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

    async def close(self):
        """
        Close writer stream as soon as the buffer has emptied.
        :return:
        """
        self.writer.close()
        with contextlib.suppress(Exception):
            await self.writer.wait_closed()

    async def drain(self):
        """
        Await the write buffer to empty.
        See StreamWriter.drain()

        :raises: DisconnectedError if the client disconnects while waiting for
        the write buffer to empty.
        """
        # NOTE: This sleep is needed in python versions <= 3.6
        # https://github.com/aio-libs/aioftp/issues/7
        await asyncio.sleep(0)
        async with self._drain_lock:
            try:
                await self.writer.drain()
            except Exception as e:
                await self.close()
                raise DisconnectedError("Protocol connection lost!") from e

    async def send_message(self, message: dict):
        await self.send_raw(self.encode_message(message))

    async def send_messages(self, messages):
        metrics.sent_messages.inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        payload = [self.encode_message(msg) for msg in messages]
        self.writer.writelines(payload)
        await self.drain()

    async def send_raw(self, data):
        metrics.sent_messages.inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        self.writer.write(data)
        # NOTE: This try/except is for debugging purposes only. In the log we
        # are seeing "Task exception was never retrieved" errors for
        # `send_message` and `send_raw` but the stack trace does not tell us
        # enough to determine which tasks are generating them. We include the
        # message contents here to help determine the cause.
        try:
            await self.drain()
        except DisconnectedError as e:
            raise DisconnectedError(data) from e

    def write(self, message):
        """
        Write data to the socket without waiting for it to be sent. This should
        only be used when forwarding data from one connection to another.
        """
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        self.write_raw(self.encode_message(message))

    def write_raw(self, data):
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        self.writer.write(data)
