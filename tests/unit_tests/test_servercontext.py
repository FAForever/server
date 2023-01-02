from unittest import mock

import pytest

from server import LobbyConnection, ServerContext
from server.protocol import Protocol


@pytest.fixture
def context():
    return ServerContext("TestServer", mock.Mock, [])


def test_repr(context):
    text = repr(context)

    assert context.__class__.__name__ in text
    assert "TestServer" in text


async def test_stop_unstarted(context):
    context = ServerContext("TestServer", mock.Mock, [])

    await context.stop()


def test_write_broadcast_raw_error(context, caplog):
    conn = mock.create_autospec(LobbyConnection)
    proto = mock.create_autospec(Protocol)
    proto.write_raw.side_effect = RuntimeError("test")

    context.connections[conn] = proto

    with caplog.at_level("ERROR"):
        context.write_broadcast_raw(b"foo")

    assert "TestServer: Encountered error in broadcast" in caplog.text


def test_suppress_and_log_regular_function(context, caplog):
    def on_connection_lost():
        raise RuntimeError("test")

    with caplog.at_level("WARNING"):
        with context.suppress_and_log(on_connection_lost, Exception):
            on_connection_lost()

    assert "Unexpected exception in on_connection_lost" in caplog.text


def test_suppress_and_log_bound_method(context, caplog):
    class SomeClass:
        def on_connection_lost(self):
            raise RuntimeError("test")

    obj = SomeClass()

    with caplog.at_level("WARNING"):
        with context.suppress_and_log(obj.on_connection_lost, Exception):
            obj.on_connection_lost()

    assert "Unexpected exception in SomeClass.on_connection_lost" in caplog.text
