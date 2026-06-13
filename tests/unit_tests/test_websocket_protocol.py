import asyncio
import json
from unittest import mock

import pytest
from aiohttp import WSMsgType, web

from server.protocol import DisconnectedError, WebSocketProtocol


def test_encode_decode_roundtrip():
    payload = {"command": "ping", "value": 42, "nested": {"a": [1, 2, 3]}}
    encoded = WebSocketProtocol.encode_message(payload)
    assert isinstance(encoded, bytes)
    assert WebSocketProtocol.decode_message(encoded) == payload


def test_encode_no_newline_framing():
    encoded = WebSocketProtocol.encode_message({"command": "ping"})
    assert encoded == b'{"command":"ping"}'


async def test_read_message_text_frame():
    ws = mock.MagicMock()
    ws.closed = False
    msg = mock.Mock(type=WSMsgType.TEXT, data=json.dumps({"command": "ping"}))
    ws.receive = mock.AsyncMock(return_value=msg)

    proto = WebSocketProtocol(ws)
    assert await proto.read_message() == {"command": "ping"}


async def test_read_message_close_frame_raises():
    ws = mock.MagicMock()
    ws.closed = False
    ws.receive = mock.AsyncMock(return_value=mock.Mock(type=WSMsgType.CLOSE))

    proto = WebSocketProtocol(ws)
    with pytest.raises(DisconnectedError):
        await proto.read_message()


async def test_read_message_error_frame_raises():
    ws = mock.MagicMock()
    ws.closed = False
    ws.receive = mock.AsyncMock(return_value=mock.Mock(type=WSMsgType.ERROR))

    proto = WebSocketProtocol(ws)
    with pytest.raises(DisconnectedError):
        await proto.read_message()


async def test_write_raw_when_disconnected_raises():
    ws = mock.MagicMock()
    ws.closed = True

    proto = WebSocketProtocol(ws)
    with pytest.raises(DisconnectedError):
        proto.write_raw(b'{"command":"ping"}')


async def test_send_message_routes_through_send_str():
    ws = mock.MagicMock()
    ws.closed = False
    ws.send_str = mock.AsyncMock()

    proto = WebSocketProtocol(ws)
    await proto.send_message({"command": "ping"})

    ws.send_str.assert_awaited_once_with('{"command":"ping"}')


async def test_close_closes_owned_session():
    ws = mock.MagicMock()
    ws.close = mock.AsyncMock()
    ws.closed = False

    session = mock.MagicMock()
    session.close = mock.AsyncMock()

    proto = WebSocketProtocol(ws, owned_session=session)
    await proto.close()

    ws.close.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_end_to_end_roundtrip_against_aiohttp_server(aiohttp_unused_port):
    """The protocol can be paired with an aiohttp WebSocketResponse."""
    received: list[dict] = []
    port = aiohttp_unused_port()

    async def handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        proto = WebSocketProtocol(ws)
        msg = await proto.read_message()
        received.append(msg)
        await proto.send_message({"command": "pong"})
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/ws", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                await ws.send_str('{"command":"ping"}')
                reply = await ws.receive()
                assert reply.type == WSMsgType.TEXT
                assert json.loads(reply.data) == {"command": "pong"}
    finally:
        await runner.cleanup()

    assert received == [{"command": "ping"}]


@pytest.fixture
def aiohttp_unused_port():
    import socket

    def _free():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    return _free


# Keep asyncio quiet about unused imports.
_ = asyncio
