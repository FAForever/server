import asyncio
from contextlib import asynccontextmanager, closing
from socket import socketpair

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from server.protocol import DisconnectedError, SimpleJsonProtocol

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session")
def protocol_context():
    @asynccontextmanager
    async def make_protocol():
        rsock, wsock = socketpair()
        with closing(wsock):
            reader, writer = await asyncio.open_connection(sock=rsock)
            proto = SimpleJsonProtocol(reader, writer)
            yield proto
            await proto.close()

    return make_protocol


@pytest.fixture(scope="session")
def protocol_class():
    return SimpleJsonProtocol


@pytest.fixture
def socket_pair():
    """A pair of connected sockets."""
    rsock, wsock = socketpair()
    with closing(wsock):
        yield rsock, wsock


@pytest.fixture
async def reader_writer(socket_pair):
    """A connected StreamReader, StreamWriter pair"""
    rsock, _ = socket_pair
    # Socket closed by socket_pair fixture
    return await asyncio.open_connection(sock=rsock)


@pytest.fixture
def reader(reader_writer):
    reader, _ = reader_writer
    return reader


@pytest.fixture
def writer(reader_writer):
    _, writer = reader_writer
    return writer


@pytest.fixture
async def protocol(reader, writer):
    proto = SimpleJsonProtocol(reader, writer)
    yield proto
    await proto.close()


@pytest.fixture
async def unix_srv():
    async def do_nothing(client_reader, client_writer):
        with closing(client_writer):
            await client_reader.read()

    srv = await asyncio.start_unix_server(do_nothing, "/tmp/test.sock")

    with closing(srv):
        yield srv

    await srv.wait_closed()


@pytest.fixture
async def unix_protocol(unix_srv):
    (reader, writer) = await asyncio.open_unix_connection("/tmp/test.sock")
    proto = SimpleJsonProtocol(reader, writer)
    yield proto
    await proto.close()


def st_messages():
    """Strategy for generating internal message dictionaries"""
    return st.dictionaries(
        keys=st.text(),
        values=st.one_of(
            st.integers(),
            st.text(),
            st.lists(st.one_of(st.integers(), st.text()))
        )
    )


async def test_recv_malformed_message(protocol, reader):
    reader.feed_data(b"\0")
    reader.feed_eof()

    with pytest.raises(Exception):
        await protocol.read_message()


@given(message=st_messages())
@example(message={
    "Some": "crazy",
    "Message": ["message", 10],
    "with": 1000
})
@example(message={
    "some_header": True,
    "array": [str(i) for i in range(1520)]
})
@settings(max_examples=300)
async def test_pack_unpack(protocol_context, message):
    async with protocol_context() as protocol:
        protocol.reader.feed_data(protocol.encode_message(message))

        assert message == await protocol.read_message()


@given(message=st_messages())
@example(message={
    "Some": "crazy",
    "Message": ["message", 10],
    "with": 1000
})
async def test_deterministic(protocol_class, message):
    bytes1 = protocol_class.encode_message(message)
    bytes2 = protocol_class.encode_message(message)
    assert bytes1 == bytes2


async def test_send_message_simultaneous_writes(unix_protocol):
    msg = {
        "command": "test",
        "data": "*" * (4096*4)
    }

    # If drain calls are not synchronized, then this will raise an
    # AssertionError from within asyncio
    await asyncio.gather(*(unix_protocol.send_message(msg) for i in range(20)))


async def test_send_messages_simultaneous_writes(unix_protocol):
    msg = {
        "command": "test",
        "data": "*" * (4096*4)
    }

    # If drain calls are not synchronized, then this will raise an
    # AssertionError from within asyncio
    await asyncio.gather(*(
        unix_protocol.send_messages((msg, msg)) for i in range(20))
    )


async def test_send_raw_simultaneous_writes(unix_protocol):
    msg = b"*" * (4096*4)

    # If drain calls are not synchronized, then this will raise an
    # AssertionError from within asyncio
    await asyncio.gather(*(unix_protocol.send_raw(msg) for i in range(20)))


async def test_send_connected_attribute(unix_protocol, unix_srv):
    unix_protocol.reader.set_exception(
        RuntimeError("Unit test triggered exception")
    )

    with pytest.raises(DisconnectedError):
        await unix_protocol.send_message({"Hello": "World"})

    assert unix_protocol.is_connected() is False


async def test_send_when_disconnected(protocol):
    await protocol.close()

    assert protocol.is_connected() is False

    with pytest.raises(DisconnectedError):
        await protocol.send_message({"some": "message"})

    with pytest.raises(DisconnectedError):
        await protocol.send_messages([
            {"some": "message"},
            {"some": "other message"}
        ])


async def test_read_when_disconnected(protocol):
    await protocol.close()

    assert protocol.is_connected() is False

    with pytest.raises(DisconnectedError):
        await protocol.read_message()
