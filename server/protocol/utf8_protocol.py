import json
from asyncio import IncompleteReadError, StreamReader, StreamWriter
from json.decoder import JSONDecodeError
from typing import List

import server

from .protocol import Protocol


class UTF8Protocol(Protocol):
    """ Implements a UTF-8 based encoding scheme """

    def __init__(self, reader: StreamReader, writer: StreamWriter):
        """
        Initialize the protocol

        :param StreamReader reader: asyncio stream to read from
        """
        self.reader = reader
        self.writer = writer

    async def read_message(self) -> dict:
        """
        Asynchronously read a message from the stream

        :raises: IncompleteReadError, UnicodeDecodeError, JSONDecodeError
        :return dict: Parsed message
        """
        message = await self.reader.readline()
        return json.loads(message.decode('utf8'))

    def send_message(self, message: dict) -> None:
        """
        Send a single message in the form of a dictionary

        :param message: Message to send
        """
        data = (json.dumps(message) + "\n").encode('utf8')
        self.send_raw(data)

    def send_messages(self, messages: List[dict]) -> None:
        """
        Send multiple messages in the form of a list of dictionaries.

        May be more optimal than sending a single message.

        :param messages:
        """
        for message in messages:
            self.send_message(message)

    def send_raw(self, data: bytes) -> None:
        """
        Send raw bytes. Should generally not be used.

        :param data: bytes to send
        """
        server.stats.incr('server.sent_messages')
        self.writer.write(data)

    async def drain(self) -> None:
        """
        Await the write buffer to empty
        """
        await self.writer.drain()

    def close(self) -> None:
        """
        Close the stream
        """
        self.writer.close()
