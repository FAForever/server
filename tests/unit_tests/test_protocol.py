import asyncio
import struct
from asyncio import StreamReader
from unittest import mock

import pytest
from server.protocol import QDataStreamProtocol

pytestmark = pytest.mark.asyncio


@pytest.fixture
def reader(event_loop):
    return StreamReader(loop=event_loop)


@pytest.fixture
def writer():
    return mock.Mock()


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
def unix_protocol(unix_srv, event_loop):
    (reader, writer) = event_loop.run_until_complete(
        asyncio.open_unix_connection('/tmp/test.sock')
    )
    protocol = QDataStreamProtocol(reader, writer)
    yield protocol

    protocol.close()


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
