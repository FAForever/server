import asyncio
from unittest import mock

import pytest
from asynctest import CoroutineMock, exhaust_callbacks
from server import ServerContext, fake_statsd
from server.lobbyconnection import LobbyConnection
from server.protocol import QDataStreamProtocol

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_server(event_loop):
    class MockServer:
        def __init__(self):
            self.protocol, self.peername, self.user_agent = None, None, None
            self.on_connection_lost = CoroutineMock()

        async def on_connection_made(self, protocol, peername):
            self.protocol = protocol
            self.peername = peername
            self.protocol.writer.write_eof()
            self.protocol.reader.feed_eof()

        async def on_message_received(self, msg):
            pass

    return MockServer()


@pytest.fixture
def mock_context(event_loop, request, mock_server):
    ctx = ServerContext(lambda: mock_server, name='TestServer')

    def fin():
        ctx.close()
    request.addfinalizer(fin)
    return event_loop.run_until_complete(ctx.listen('127.0.0.1', None)), ctx


@pytest.fixture
def context(event_loop, request):
    def make_connection() -> LobbyConnection:
        return LobbyConnection(
            database=mock.Mock(),
            geoip=mock.Mock(),
            games=mock.Mock(),
            nts_client=mock.Mock(),
            players=mock.Mock(),
            ladder_service=mock.Mock()
        )

    ctx = ServerContext(make_connection, name='TestServer')

    def fin():
        ctx.close()
    request.addfinalizer(fin)
    return event_loop.run_until_complete(ctx.listen('127.0.0.1', None)), ctx


async def test_serverside_abort(event_loop, mock_context, mock_server):
    srv, ctx = mock_context
    (reader, writer) = await asyncio.open_connection(*srv.sockets[0].getsockname())
    proto = QDataStreamProtocol(reader, writer)
    await proto.send_message({"some_junk": True})
    await exhaust_callbacks(event_loop)

    mock_server.on_connection_lost.assert_any_call()


async def test_broadcast_raw(context, mock_server):
    srv, ctx = context
    (reader, writer) = await asyncio.open_connection(
        *srv.sockets[0].getsockname()
    )
    writer.close()

    # If connection errors aren't handled, this should fail due to a
    # ConnectionError
    for _ in range(20):
        await ctx.broadcast_raw(b"Some bytes")


async def test_server_fake_statsd():
    dummy = fake_statsd.DummyConnection()
    # Verify that no exceptions are raised
    with dummy.timer('a'):
        dummy.incr('a')
        dummy.gauge('a', 'b', delta=True)
        dummy.Unit()
