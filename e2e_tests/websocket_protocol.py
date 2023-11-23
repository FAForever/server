import asyncio
import contextlib
from unittest import mock

import websockets

from server.protocol import DisconnectedError, Protocol


class WebsocketProtocol:
    def __init__(
        self,
        websocket: websockets.client.WebSocketClientProtocol,
        protocol_class: type[Protocol],
    ):
        self.websocket = websocket
        reader = asyncio.StreamReader()
        reader.set_transport(asyncio.ReadTransport())
        self.proto = protocol_class(
            reader,
            mock.create_autospec(asyncio.StreamWriter)
        )

    def is_connected(self) -> bool:
        """
        Return whether or not the connection is still alive
        """
        return self.websocket.open

    async def read_message(self) -> dict:
        if self.proto.reader._buffer:
            # If buffer contains partial data, this await call could hang.
            return await self.proto.read_message()

        msg = await self.websocket.recv()
        self.proto.reader.feed_data(msg)
        # msg should always contain at least 1 complete message.
        # If it contains partial data, this await call could hang.
        return await self.proto.read_message()

    async def send_message(self, message: dict) -> None:
        """
        Send a single message in the form of a dictionary

        # Errors
        May raise `DisconnectedError`.
        """
        await self.send_raw(self.proto.encode_message(message))

    async def send_messages(self, messages: list[dict]) -> None:
        """
        Send multiple messages in the form of a list of dictionaries.

        # Errors
        May raise `DisconnectedError`.
        """
        for message in messages:
            await self.send_message(message)

    async def send_raw(self, data: bytes) -> None:
        """
        Send raw bytes. Should generally not be used.

        # Errors
        May raise `DisconnectedError`.
        """
        try:
            await self.websocket.send(data)
        except websockets.exceptions.ConnectionClosedOK:
            raise DisconnectedError("The websocket connection was closed")
        except websockets.exceptions.ConnectionClosed as e:
            raise DisconnectedError("Websocket connection lost!") from e

    def abort(self) -> None:
        # SelectorTransport only
        self.websocket.transport.abort()

    async def close(self) -> None:
        """
        Close the websocket connection.

        # Errors
        Never raises. Any exceptions that occur while waiting to close are
        ignored.
        """
        with contextlib.suppress(Exception):
            await self.websocket.close()
