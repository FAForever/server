import asyncio
from unittest import mock

import pytest
from asynctest import exhaust_callbacks
from server import ServerContext, fake_statsd
from server.protocol import QDataStreamProtocol

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_server(event_loop):
    class MockServer:
        def __init__(self):
            self.protocol, self.peername, self.user_agent = None, None, None

        @asyncio.coroutine
        def on_connection_made(self, protocol, peername):
            self.protocol = protocol
            self.peername = peername
            self.protocol.writer.write_eof()
            self.protocol.reader.feed_eof()

        @asyncio.coroutine
        def on_message_received(self, msg):
            pass
    mock_server = MockServer()
    mock_server.on_connection_lost = mock.Mock()
    return mock_server


@pytest.fixture
def mock_context(event_loop, request, mock_server):
    ctx = ServerContext(lambda: mock_server, None, name='TestServer')

    def fin():
        ctx.close()
    request.addfinalizer(fin)
    return event_loop.run_until_complete(ctx.listen('127.0.0.1', None))


async def test_serverside_abort(event_loop, mock_context, mock_server):
    (reader, writer) = await asyncio.open_connection(*mock_context.sockets[0].getsockname())
    proto = QDataStreamProtocol(reader, writer)
    await proto.send_message({"some_junk": True})
    await exhaust_callbacks(event_loop)

    mock_server.on_connection_lost.assert_any_call()


async def test_server_fake_statsd():
    dummy = fake_statsd.DummyConnection()
    # Verify that no exceptions are raised
    with dummy.timer('a'):
        dummy.incr('a')
        dummy.gauge('a', 'b', delta=True)
        dummy.unit()
