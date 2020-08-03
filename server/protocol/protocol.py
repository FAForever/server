import contextlib
from abc import ABCMeta, abstractmethod
from asyncio import StreamReader, StreamWriter
from typing import List

import server.metrics as metrics

from ..asyncio_extensions import synchronizedmethod


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

        :raises: IncompleteReadError
        :return dict: Parsed message
        """
        pass  # pragma: no cover

    async def send_message(self, message: dict) -> None:
        """
        Send a single message in the form of a dictionary

        :param message: Message to send
        :raises: DisconnectedError
        """
        await self.send_raw(self.encode_message(message))

    async def send_messages(self, messages: List[dict]) -> None:
        """
        Send multiple messages in the form of a list of dictionaries.

        May be more optimal than sending a single message.

        :param messages:
        :raises: DisconnectedError
        """
        self.write_messages(messages)
        await self.drain()

    async def send_raw(self, data: bytes) -> None:
        """
        Send raw bytes. Should generally not be used.

        :param data: bytes to send
        :raises: DisconnectedError
        """
        self.write_raw(data)
        await self.drain()

    def write_message(self, message: dict) -> None:
        """
        Write a single message into the message buffer. Should be used when
        sending broadcasts or when sending messages that are triggered by
        incoming messages from other players.

        :param message: Message to send
        """
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        self.write_raw(self.encode_message(message))

    def write_messages(self, messages: List[dict]) -> None:
        """
        Write multiple message into the message buffer.

        :param messages: List of messages to write
        """
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        self.writer.writelines([self.encode_message(msg) for msg in messages])

    def write_raw(self, data: bytes) -> None:
        """
        Write raw bytes into the message buffer. Should generally not be used.

        :param data: bytes to send
        """
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        self.writer.write(data)

    async def close(self) -> None:
        """
        Close the underlying writer as soon as the buffer has emptied.
        :return:
        """
        self.writer.close()
        with contextlib.suppress(Exception):
            await self.writer.wait_closed()

    @synchronizedmethod
    async def drain(self) -> None:
        """
        Await the write buffer to empty.
        See StreamWriter.drain()

        :raises: DisconnectedError if the client disconnects while waiting for
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
