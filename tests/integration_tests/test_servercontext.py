import asyncio
import pytest
from unittest import mock

from server import ServerContext
from server.protocol import QDataStreamProtocol
from server import fake_statsd


@pytest.fixture
def mock_server(loop):
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
def mock_context(loop, request, mock_server):
    ctx = ServerContext(lambda: mock_server, loop, name='TestServer')

    def fin():
        ctx.close()
    request.addfinalizer(fin)
    return loop.run_until_complete(ctx.listen('127.0.0.1', None))

@asyncio.coroutine
def test_serverside_abort(loop, mock_context, mock_server):
    (reader, writer) = yield from asyncio.open_connection(*mock_context.sockets[0].getsockname())
    proto = QDataStreamProtocol(reader, writer)
    proto.send_message({"some_junk": True})
    yield from writer.drain()
    yield from asyncio.sleep(0.1)

    mock_server.on_connection_lost.assert_any_call()

def test_server_fake_statsd():
    dummy = fake_statsd.DummyConnection()
    try:
        with dummy.timer('a'):
            dummy.incr('a')
            dummy.gauge('a', 'b', delta=True)
            unit = dummy.unit()

    except:
        pytest.fail("StatsD connection dummy raises exception when used")

