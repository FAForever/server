import asyncio
import contextlib
from unittest import mock

import asynctest
import pytest
from asynctest import CoroutineMock, exhaust_callbacks

from server import ServerContext
from server.core import Service
from server.lobbyconnection import LobbyConnection
from server.protocol import DisconnectedError, QDataStreamProtocol

pytestmark = pytest.mark.asyncio


class MockConnection:
    def __init__(self):
        self.protocol = None
        self.peername = None
        self.user_agent = None
        self.version = None
        self.on_connection_lost = CoroutineMock()

    async def on_connection_made(self, protocol, peername):
        self.protocol = protocol
        self.peername = peername
        self.protocol.writer.write_eof()
        self.protocol.reader.feed_eof()

    async def on_message_received(self, msg):
        pass


@pytest.fixture
def mock_connection():
    return MockConnection()


@pytest.fixture
def mock_service():
    return asynctest.create_autospec(Service)


@pytest.fixture
async def mock_context(mock_connection, mock_service):
    ctx = ServerContext("TestServer", lambda: mock_connection, [mock_service])
    yield await ctx.listen("127.0.0.1", None), ctx
    ctx.close()


@pytest.fixture
async def context(mock_service):
    def make_connection() -> LobbyConnection:
        return LobbyConnection(
            database=mock.Mock(),
            game_service=mock.Mock(),
            players=mock.Mock(),
            nts_client=mock.Mock(),
            geoip=mock.Mock(),
            ladder_service=mock.Mock(),
            party_service=mock.Mock(),
            oauth_service=mock.Mock()
        )

    ctx = ServerContext("TestServer", make_connection, [mock_service])
    yield await ctx.listen("127.0.0.1", None), ctx
    ctx.close()


async def test_serverside_abort(
    event_loop,
    mock_context,
    mock_connection,
    mock_service
):
    srv, ctx = mock_context
    (reader, writer) = await asyncio.open_connection(*srv.sockets[0].getsockname())
    proto = QDataStreamProtocol(reader, writer)
    await proto.send_message({"some_junk": True})
    await exhaust_callbacks(event_loop)

    mock_connection.on_connection_lost.assert_any_call()
    mock_service.on_connection_lost.assert_called_once()


async def test_connection_broken_external(context):
    """
    When the connection breaks while the server is calling protocol.send from
    somewhere other than the main read - response loop. Make sure that this
    still triggers the proper connection cleanup.
    """
    srv, ctx = context
    (reader, writer) = await asyncio.open_connection(
        *srv.sockets[0].getsockname()
    )
    writer.close()
    # Need this sleep for test to work, otherwise closed protocol isn't detected
    await asyncio.sleep(0)

    proto = next(iter(ctx.connections.values()))
    proto.writer.transport.set_write_buffer_limits(high=0)

    # Might raise DisconnectedError depending on OS
    with contextlib.suppress(DisconnectedError):
        await proto.send_message({"command": "Some long message" * 4096})

    await asyncio.sleep(0.1)
    assert len(ctx.connections) == 0
