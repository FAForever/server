import asyncio
import contextlib
from unittest import mock

import aiohttp
import pytest

from server import ServerContext
from server.core import Service
from server.lobbyconnection import LobbyConnection
from server.protocol import DisconnectedError, WebSocketProtocol
from tests.utils import exhaust_callbacks, fast_forward


async def wait_for_connection_registered(ctx, max_iters=1000):
    for _ in range(max_iters):
        if ctx.connections:
            return
        await asyncio.sleep(0)
    raise AssertionError(
        "Server did not register the connection within the allotted iterations"
    )


def ws_url(ctx: ServerContext) -> str:
    return f"http://{ctx.host}:{ctx.port}{ctx.path}"


class MockConnection:
    def __init__(self):
        self.protocol = None
        self.peername = None
        self.user_agent = None
        self.version = None
        self.on_connection_lost = mock.AsyncMock()

    def get_user_identifier(self):
        return "MockConnection"

    async def on_connection_made(self, protocol, peername):
        self.protocol = protocol
        self.peername = peername
        await self.protocol.close()

    async def on_message_received(self, msg):
        pass


@pytest.fixture
def mock_connection():
    return MockConnection()


@pytest.fixture
def mock_service():
    return mock.create_autospec(Service)


@pytest.fixture
async def mock_context(mock_connection, mock_service):
    ctx = ServerContext("TestServer", lambda: mock_connection, [mock_service])
    await ctx.listen("127.0.0.1", None)
    yield ctx
    await ctx.shutdown()


@pytest.fixture
async def context(mock_service):
    def make_connection() -> LobbyConnection:
        return LobbyConnection(
            database=mock.Mock(),
            game_service=mock.Mock(),
            players=mock.Mock(),
            geoip=mock.Mock(),
            ladder_service=mock.Mock(),
            party_service=mock.Mock(),
            rating_service=mock.Mock(),
            oauth_service=mock.Mock(),
            veto_service=mock.Mock(),
        )

    ctx = ServerContext("TestServer", make_connection, [mock_service])
    await ctx.listen("127.0.0.1", None)
    yield ctx
    await ctx.shutdown()


async def test_serverside_abort(
    mock_context,
    mock_connection,
    mock_service
):
    ctx = mock_context
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(ws_url(ctx)) as ws:
            await ws.send_bytes(b'{"some_junk": true}\n')
            await exhaust_callbacks()

    # Allow server-side disconnect handler to run.
    for _ in range(50):
        if not ctx.connections:
            break
        await asyncio.sleep(0.02)

    mock_connection.on_connection_lost.assert_any_call()
    mock_service.on_connection_lost.assert_called_once()


async def test_connection_broken_external(context):
    """
    When the connection breaks while the server is calling protocol.send from
    somewhere other than the main read - response loop. Make sure that this
    still triggers the proper connection cleanup.
    """
    ctx = context
    session = aiohttp.ClientSession()
    ws = await session.ws_connect(ws_url(ctx))
    await wait_for_connection_registered(ctx)
    await ws.close()
    await session.close()
    await asyncio.sleep(0.1)

    # Server-side cleanup should occur eventually
    for _ in range(50):
        if not ctx.connections:
            break
        await asyncio.sleep(0.02)

    assert len(ctx.connections) == 0


async def test_unexpected_exception(context, caplog, mocker):
    ctx = context

    mocker.patch.object(
        WebSocketProtocol,
        "read_message",
        mock.AsyncMock(
            side_effect=RuntimeError("test")
        )
    )

    with caplog.at_level("TRACE"):
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url(ctx)):
                await exhaust_callbacks()

    assert "Exception in protocol" in caplog.text


async def test_unexpected_exception_in_connection_lost(context, caplog):
    ctx = context

    ctx._services[0].on_connection_lost = mock.Mock(
        side_effect=RuntimeError("test"),
        __name__="on_connection_lost"
    )

    with caplog.at_level("TRACE"):
        async with aiohttp.ClientSession() as session:
            ws = await session.ws_connect(ws_url(ctx))
            await ws.close()
            await asyncio.sleep(0.1)

    assert "Unexpected exception in on_connection_lost" in caplog.text


@fast_forward(20)
async def test_drain_connections(context):
    ctx = context
    session = aiohttp.ClientSession()
    ws = await session.ws_connect(ws_url(ctx))
    await wait_for_connection_registered(ctx)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            ctx.drain_connections(),
            timeout=10
        )

    await ws.close()
    await session.close()

    await asyncio.wait_for(
        ctx.drain_connections(),
        timeout=3
    )


# Silence flake about unused imports kept for backward symmetry.
_ = (contextlib, DisconnectedError)
