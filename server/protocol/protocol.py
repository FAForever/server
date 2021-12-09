import contextlib
import json
from abc import ABCMeta, abstractmethod
from asyncio import StreamReader, StreamWriter

import server.metrics as metrics

from ..asyncio_extensions import synchronizedmethod

json_encoder = json.JSONEncoder(separators=(",", ":"))


class DisconnectedError(ConnectionError):
    """For signaling that a protocol has lost connection to the remote."""


class Protocol(metaclass=ABCMeta):
    def __init__(self, reader: StreamReader, writer: StreamWriter):
        self.reader = reader
        self.writer = writer
        # Force calls to drain() to only return once the data has been sent
        self.writer.transport.set_write_buffer_limits(high=0)

    @staticmethod
    @abstractmethod
    def encode_message(message: dict) -> bytes:
        """
        Encode a message as raw bytes. Can be used along with `*_raw` methods.
        """
        pass  # pragma: no cover

    def is_connected(self) -> bool:
        """
        Return whether or not the connection is still alive
        """
        return not self.writer.is_closing()

    @abstractmethod
    async def read_message(self) -> dict:
        """
        Asynchronously read a message from the stream

        # Returns
        The parsed message

        # Errors
        May raise `IncompleteReadError`.
        """
        pass  # pragma: no cover

    async def send_message(self, message: dict) -> None:
        """
        Send a single message in the form of a dictionary

        # Errors
        May raise `DisconnectedError`.
        """
        await self.send_raw(self.encode_message(message))

    async def send_messages(self, messages: list[dict]) -> None:
        """
        Send multiple messages in the form of a list of dictionaries.

        May be more optimal than sending a single message.

        # Errors
        May raise `DisconnectedError`.
        """
        self.write_messages(messages)
        await self.drain()

    async def send_raw(self, data: bytes) -> None:
        """
        Send raw bytes. Should generally not be used.

        # Errors
        May raise `DisconnectedError`.
        """
        self.write_raw(data)
        await self.drain()

    def write_message(self, message: dict) -> None:
        """
        Write a single message into the message buffer. Should be used when
        sending broadcasts or when sending messages that are triggered by
        incoming messages from other players.

        # Errors
        May raise `DisconnectedError`.
        """
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        self.write_raw(self.encode_message(message))

    def write_messages(self, messages: list[dict]) -> None:
        """
        Write multiple message into the message buffer.

        # Errors
        May raise `DisconnectedError`.
        """
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        self.writer.writelines([self.encode_message(msg) for msg in messages])

    def write_raw(self, data: bytes) -> None:
        """
        Write raw bytes into the message buffer. Should generally not be used.

        # Errors
        May raise `DisconnectedError`.
        """
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        self.writer.write(data)

    def abort(self) -> None:
        # SelectorTransport only
        self.writer.transport.abort()

    async def close(self) -> None:
        """
        Close the underlying writer as soon as the buffer has emptied.

        # Errors
        Never raises. Any exceptions that occur while waiting to close are
        ignored.
        """
        self.writer.close()
        with contextlib.suppress(Exception):
            await self.writer.wait_closed()

    @synchronizedmethod
    async def drain(self) -> None:
        """
        Await the write buffer to empty.
        See StreamWriter.drain()

        # Errors
        Raises `DisconnectedError` if the client disconnects while waiting for
        the write buffer to empty.
        """
        # Method needs to be synchronized as drain() cannot be called
        # concurrently by multiple coroutines:
        # http://bugs.python.org/issue29930.
        try:
            await self.writer.drain()
        except Exception as e:
            await self.close()
            raise DisconnectedError("Protocol connection lost!") from e
