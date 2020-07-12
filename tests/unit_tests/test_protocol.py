import asyncio
import json
import struct
from socket import socketpair

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from server.protocol import DisconnectedError, QDataStreamProtocol

pytestmark = pytest.mark.asyncio


@pytest.fixture
def socket_pair():
    """A pair of connected sockets."""
    return socketpair()


@pytest.fixture
async def reader_writer(socket_pair):
    """A connected StreamReader, StreamWriter pair"""
    rsock, _ = socket_pair
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
def protocol(reader, writer):
    return QDataStreamProtocol(reader, writer)


@pytest.fixture
def unix_srv(event_loop):
    async def do_nothing(client_reader, client_writer):
        await client_reader.read()

    srv = event_loop.run_until_complete(
        asyncio.start_unix_server(do_nothing, '/tmp/test.sock')
    )

    yield srv

    srv.close()
    event_loop.run_until_complete(srv.wait_closed())


@pytest.fixture
async def unix_protocol(unix_srv):
    (reader, writer) = await asyncio.open_unix_connection('/tmp/test.sock')
    protocol = QDataStreamProtocol(reader, writer)
    yield protocol

    await protocol.close()


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


async def test_types():
    with pytest.raises(NotImplementedError):
        QDataStreamProtocol.pack_message({"Not": ["a", "string"]})


async def test_QDataStreamProtocol_recv_small_message(protocol, reader):
    data = QDataStreamProtocol.pack_block(b''.join([QDataStreamProtocol.pack_qstring('{"some_header": true}'),
                                                    QDataStreamProtocol.pack_qstring('Goodbye')]))
    reader.feed_data(data)

    message = await protocol.read_message()

    assert message == {'some_header': True, 'legacy': ['Goodbye']}


async def test_QDataStreamProtocol_recv_malformed_message(protocol, reader):
    reader.feed_data(b'\0')
    reader.feed_eof()

    with pytest.raises(asyncio.IncompleteReadError):
        await protocol.read_message()


async def test_QDataStreamProtocol_recv_large_array(protocol, reader):
    reader.feed_data(QDataStreamProtocol.pack_block(b''.join(
        [QDataStreamProtocol.pack_qstring('{"some_header": true}')] +
        [QDataStreamProtocol.pack_qstring(str(i)) for i in range(1520)])))
    reader.feed_eof()

    message = await protocol.read_message()

    assert message == {'some_header': True, 'legacy': [str(i) for i in range(1520)]}


async def test_unpacks_evil_qstring(protocol, reader):
    reader.feed_data(struct.pack('!I', 64))
    reader.feed_data(b'\x00\x00\x004\x00{\x00"\x00c\x00o\x00m\x00m\x00a\x00n\x00d\x00"\x00:\x00 \x00"\x00a\x00s\x00k\x00_\x00s\x00e\x00s\x00s\x00i\x00o\x00n\x00"\x00}\xff\xff\xff\xff\xff\xff\xff\xff')
    reader.feed_eof()

    message = await protocol.read_message()

    assert message == {'command': 'ask_session'}


@pytest.mark.filterwarnings("ignore:.*'(protocol|reader)' fixture")
@given(message=st_messages())
@example(message={
    "Some": "crazy",
    "Message": ["message", 10],
    "with": 1000
})
@settings(max_examples=300)
async def test_QDataStreamProtocol_pack_unpack(protocol, reader, message):
    reader.feed_data(QDataStreamProtocol.pack_message(json.dumps(message)))

    assert message == await protocol.read_message()


@given(message=st_messages())
@example(message={
    "Some": "crazy",
    "Message": ["message", 10],
    "with": 1000
})
async def test_QDataStreamProtocol_deterministic(message):
    assert (
        QDataStreamProtocol.encode_message(message) ==
        QDataStreamProtocol.encode_message(message) ==
        QDataStreamProtocol.encode_message(message)
    )


async def test_QDataStreamProtocol_encode_ping_pong():
    assert QDataStreamProtocol.encode_message({"command": "ping"}) == \
        b"\x00\x00\x00\x0c\x00\x00\x00\x08\x00P\x00I\x00N\x00G"
    assert QDataStreamProtocol.encode_message({"command": "pong"}) == \
        b"\x00\x00\x00\x0c\x00\x00\x00\x08\x00P\x00O\x00N\x00G"


async def test_send_message_simultaneous_writes(unix_protocol):
    msg = {
        "command": "test",
        "data": '*' * (4096*4)
    }

    # If drain calls are not synchronized, then this will raise an
    # AssertionError from within asyncio
    await asyncio.gather(*(unix_protocol.send_message(msg) for i in range(20)))


async def test_send_messages_simultaneous_writes(unix_protocol):
    msg = {
        "command": "test",
        "data": '*' * (4096*4)
    }

    # If drain calls are not synchronized, then this will raise an
    # AssertionError from within asyncio
    await asyncio.gather(*(
        unix_protocol.send_messages((msg, msg)) for i in range(20))
    )


async def test_send_raw_simultaneous_writes(unix_protocol):
    msg = b'*' * (4096*4)

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
