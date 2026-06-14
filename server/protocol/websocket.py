"""WebSocket wire protocol: newline-terminated JSON inside binary WS frames."""

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
        # Trailing newline kept for client compatibility: the Kotlin lobby
        # client (faf-commons-lobby) splits incoming WS payload bytes on '\n'
        # and only emits a message once it sees the delimiter, regardless of
        # WebSocket frame boundaries.
        return (json_encoder.encode(message) + "\n").encode()

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

        # Send as a binary frame: the legacy Python desktop client (PyQt6
        # QWebSocket) only listens on binaryMessageReceived, and the Kotlin
        # client reads the raw byte stream as UTF-8 regardless of frame type,
        # so binary is the lowest common denominator.
        if isinstance(data, str):
            data = data.encode()
        task = asyncio.create_task(self.ws.send_bytes(data))
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
