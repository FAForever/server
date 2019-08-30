from asyncio import StreamReader

import asyncio
from unittest import mock
import pytest
import struct

from server.protocol import QDataStreamProtocol

pytestmark = pytest.mark.asyncio


@pytest.fixture
def reader(loop):
    return StreamReader(loop=loop)

@pytest.fixture
def writer():
    return mock.Mock()

@pytest.fixture
def protocol(reader, writer):
    return QDataStreamProtocol(reader, writer)


async def test_QDataStreamProtocol_recv_small_message(protocol,reader):
    data = QDataStreamProtocol.pack_block(b''.join([QDataStreamProtocol.pack_qstring('{"some_header": true}'),
                                                    QDataStreamProtocol.pack_qstring('Goodbye')]))
    reader.feed_data(data)

    message =await protocol.read_message()

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
