"""A WebSocket-native wire protocol.

Each message is sent as exactly one WebSocket text frame containing a single
JSON object. No newline framing — frame boundaries delimit messages.
"""

import asyncio
import contextlib
import json

from aiohttp import WSMsgType

import server.metrics as metrics

from .protocol import DisconnectedError, Protocol, json_encoder


class WebSocketProtocol(Protocol):
    def __init__(self, ws, owned_session=None):
        """Wrap an aiohttp WebSocket; optionally own a ClientSession to close."""
        # Intentionally bypass Protocol.__init__: it expects a StreamReader /
        # StreamWriter pair, which we do not have here.
        self.ws = ws
        self._pending: set[asyncio.Task] = set()
        self._owned_session = owned_session

    @staticmethod
    def encode_message(message: dict) -> bytes:
        return json_encoder.encode(message).encode()

    @staticmethod
    def decode_message(data: bytes) -> dict:
        return json.loads(data)

    def is_connected(self) -> bool:
        return not self.ws.closed

    async def read_message(self) -> dict:
        msg = await self.ws.receive()
        if msg.type == WSMsgType.TEXT:
            return json.loads(msg.data)
        if msg.type == WSMsgType.BINARY:
            return json.loads(msg.data)
        raise DisconnectedError("WebSocket connection closed")

    def write_raw(self, data: bytes) -> None:
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")

        text = data.decode() if isinstance(data, (bytes, bytearray)) else data
        task = asyncio.create_task(self.ws.send_str(text))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def write_message(self, message: dict) -> None:
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")
        self.write_raw(self.encode_message(message))

    def write_messages(self, messages: list[dict]) -> None:
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")
        for message in messages:
            self.write_raw(self.encode_message(message))

    async def drain(self) -> None:
        if not self._pending:
            return
        try:
            await asyncio.gather(*self._pending)
        except Exception as e:
            await self.close()
            raise DisconnectedError("Protocol connection lost!") from e

    def abort(self) -> None:
        for task in self._pending:
            task.cancel()
        if not self.ws.closed:
            asyncio.create_task(self.ws.close())

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self.ws.close()
        if self._owned_session is not None:
            with contextlib.suppress(Exception):
                await self._owned_session.close()
            self._owned_session = None
