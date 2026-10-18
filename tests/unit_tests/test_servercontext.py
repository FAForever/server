from unittest import mock

import pytest

from server import LobbyConnection, ServerContext
from server.protocol import Protocol


@pytest.fixture
def context():
    return ServerContext("TestServer", mock.Mock, [], mock.Mock())


def test_repr(context):
    text = repr(context)

    assert context.__class__.__name__ in text
    assert "TestServer" in text


async def test_unstarted(context):
    # Does not raise
    await context.shutdown()
    await context.shutdown(None)
    await context.drain_connections()

    assert context.connections == {}


async def test_listen_declares_consumers():
    mq_service = mock.Mock()
    mq_service.declare_queue_and_consume = mock.AsyncMock(
        return_value=(mock.Mock(), "consumer-tag-1")
    )
    mq_service.publish = mock.AsyncMock()

    ctx = ServerContext("TestServer", mock.Mock, [], message_queue_service=mq_service)
    await ctx.listen(
        client_exchange="client-ex",
        session_exchange="session-ex",
        session_request_exchange="session-request-ex",
        client_routing_keys=["client.rk"],
    )

    assert mq_service.declare_queue_and_consume.await_count == 2
    # Verify state consumer declared
    state_call = mq_service.declare_queue_and_consume.await_args_list[0]
    assert state_call.kwargs["exchange_name"] == "session-ex"
    assert state_call.kwargs["routing_keys"] == ["#"]

    # Verify connection consumer declared
    client_call = mq_service.declare_queue_and_consume.await_args_list[1]
    assert client_call.kwargs["exchange_name"] == "client-ex"
    assert client_call.kwargs["routing_keys"] == ["client.rk"]

    request_call = mq_service.publish.await_args_list[1]
    assert request_call.kwargs["exchange_name"] == "session-request-ex"
    assert request_call.kwargs["routing"] == ""
    assert request_call.kwargs["reply_to"] is not None
    assert request_call.kwargs["payload"] == {}



async def test_on_state_message_connects_player():
    mq_service = mock.Mock()
    conn = mock.Mock(spec=LobbyConnection)
    conn.session = 42
    conn.on_connection_made = mock.AsyncMock()
    conn.on_external_auth = mock.AsyncMock()
    conn.on_message_received = mock.AsyncMock()
    conn.on_connection_lost = mock.AsyncMock()
    conn.get_user_identifier = mock.Mock(return_value="User#42")

    conn_factory = mock.Mock(return_value=conn)
    ctx = ServerContext("TestServer", conn_factory, [], message_queue_service=mq_service)

    incoming_msg = mock.Mock()
    incoming_msg.body = b'{"player_id": 1234, "session_id": 42, "ip": "10.0.0.1", "port": 5000, "state": {"@type": "new"}}'
    incoming_msg.headers = None
    incoming_msg.process = mock.MagicMock(return_value=mock.AsyncMock(__aenter__=mock.AsyncMock(), __aexit__=mock.AsyncMock()))

    await ctx._on_session_message(incoming_msg)

    assert conn in ctx.connections
    assert 42 in ctx.sessions

    # Clean up
    await ctx.shutdown()


async def test_on_state_message_closes_connection_when_gone_by_session():
    mq_service = mock.Mock()
    conn = mock.Mock(spec=LobbyConnection)
    conn.session = 42
    proto = mock.Mock()
    proto.close = mock.AsyncMock()

    ctx = ServerContext("TestServer", mock.Mock, [], message_queue_service=mq_service)
    ctx.connections[conn] = proto
    ctx.sessions[42] = (conn, proto)

    incoming_msg = mock.Mock()
    incoming_msg.body = b'{"player_id": 1234, "session_id": 42, "state": {"@type": "gone"}}'
    incoming_msg.headers = None
    incoming_msg.process = mock.MagicMock(return_value=mock.AsyncMock(__aenter__=mock.AsyncMock(), __aexit__=mock.AsyncMock()))

    await ctx._on_session_message(incoming_msg)

    proto.close.assert_awaited_once()


async def test_on_state_message_does_not_close_connection_without_session():
    mq_service = mock.Mock()
    conn = mock.Mock(spec=LobbyConnection)
    conn.session = 42
    conn.player = mock.Mock()
    conn.player.id = 1234
    proto = mock.Mock()
    proto.close = mock.AsyncMock()

    ctx = ServerContext("TestServer", mock.Mock, [], message_queue_service=mq_service)
    ctx.connections[conn] = proto
    ctx.sessions[42] = (conn, proto)

    incoming_msg = mock.Mock()
    incoming_msg.body = b'{"player_id": 1234, "state": {"@type": "gone"}}'
    incoming_msg.headers = None
    incoming_msg.process = mock.MagicMock(return_value=mock.AsyncMock(__aenter__=mock.AsyncMock(), __aexit__=mock.AsyncMock()))

    await ctx._on_session_message(incoming_msg)

    proto.close.assert_not_called()


async def test_on_client_message_routes_to_session():
    mq_service = mock.Mock()
    conn = mock.Mock(spec=LobbyConnection)
    conn.session = 42
    proto = mock.Mock()
    proto.queue = mock.AsyncMock()
    proto.queue.put = mock.AsyncMock()

    ctx = ServerContext("TestServer", mock.Mock, [], message_queue_service=mq_service)
    ctx.connections[conn] = proto
    ctx.sessions[42] = (conn, proto)

    incoming_msg = mock.Mock()
    incoming_msg.body = b'{"target": {"@type": "session", "session_id": 42}, "message": {"command": "ping"}}'
    incoming_msg.headers = None
    incoming_msg.process = mock.MagicMock(return_value=mock.AsyncMock(__aenter__=mock.AsyncMock(), __aexit__=mock.AsyncMock()))

    await ctx._on_client_message(incoming_msg)

    proto.queue.put.assert_awaited_once_with({"command": "ping"})


async def test_write_broadcast():
    conn1 = mock.Mock(spec=LobbyConnection)
    proto1 = mock.Mock()
    proto1.is_connected.return_value = True

    conn2 = mock.Mock(spec=LobbyConnection)
    proto2 = mock.Mock()
    proto2.is_connected.return_value = False

    ctx = ServerContext("TestServer", mock.Mock, [], message_queue_service=(mock.Mock()))
    ctx.connections[conn1] = proto1
    ctx.connections[conn2] = proto2

    ctx.write_broadcast({"command": "ping"})

    proto1.write_message.assert_called_once_with({"command": "ping"})
    proto2.write_message.assert_not_called()


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
