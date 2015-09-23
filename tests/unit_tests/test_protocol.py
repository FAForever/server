from asyncio import StreamReader

import asyncio
from unittest import mock
import pytest
from server.protocol import QDataStreamProtocol


@pytest.fixture
def reader(loop):
    return StreamReader(loop=loop)

@pytest.fixture
def writer():
    return mock.Mock()

@pytest.fixture
def protocol(reader, writer):
    return QDataStreamProtocol(reader, writer)


@asyncio.coroutine
def test_QDataStreamProtocol_recv_small_message(protocol,reader):
    data = QDataStreamProtocol.pack_block(b''.join([QDataStreamProtocol.pack_qstring('{"some_header": true}'),
                                                    QDataStreamProtocol.pack_qstring('Goodbye')]))
    reader.feed_data(data)

    message = yield from protocol.read_message()

    assert message == {'some_header': True, 'legacy': ['Goodbye']}


@asyncio.coroutine
def test_QDataStreamProtocol_recv_malformed_message(protocol, reader):
    reader.feed_data(b'\0')
    reader.feed_eof()

    with pytest.raises(asyncio.IncompleteReadError):
        yield from protocol.read_message()

@asyncio.coroutine
def test_QDataStreamProtocol_recv_large_array(protocol, reader):
    reader.feed_data(QDataStreamProtocol.pack_block(b''.join(
        [QDataStreamProtocol.pack_qstring('{"some_header": true}')] +
        [QDataStreamProtocol.pack_qstring(str(i)) for i in range(1520)])))
    reader.feed_eof()

    message = yield from protocol.read_message()

    assert message == {'some_header': True, 'legacy': [str(i) for i in range(1520)]}


