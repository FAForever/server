from asyncio import StreamReader
import asyncio
from PySide.QtCore import QByteArray, QDataStream, QIODevice
import pytest
from server.protocol import QDataStreamProtocol


def preparePacket(action, *args, **kwargs):
    """
    Reference implementation of Qt packets
    """
    reply = QByteArray()
    stream = QDataStream(reply, QIODevice.WriteOnly)
    stream.setVersion(QDataStream.Qt_4_2)
    stream.writeUInt32(0)
    stream.writeQString(action)
    for arg in args:
        if isinstance(arg, str):
            stream.writeQString(str(arg))
    stream.device().seek(0)
    stream.writeUInt32(reply.size() - 4)

    return reply

@pytest.fixture
def reader(loop):
    return StreamReader(loop=loop)


@asyncio.coroutine
def test_QDataStreamProtocol_recv_small_message(reader):
    data = QDataStreamProtocol.pack_block(b''.join([QDataStreamProtocol.pack_qstring('Hello'),
                                                    QDataStreamProtocol.pack_qstring('Goodbye')]))
    reader.feed_data(data)
    protocol = QDataStreamProtocol(reader)

    message = yield from protocol.read_message()

    assert message == {'legacy': ['Hello', 'Goodbye']}


@asyncio.coroutine
def test_QDataStreamProtocol_recv_malformed_message(reader):
    reader.feed_data(b'\0')
    reader.feed_eof()
    protocol = QDataStreamProtocol(reader)

    with pytest.raises(asyncio.IncompleteReadError):
        yield from protocol.read_message()


@asyncio.coroutine
def test_QDataStreamProtocol_recv_large_array(reader):
    protocol = QDataStreamProtocol(reader)

    reader.feed_data(QDataStreamProtocol.pack_block(b''.join([QDataStreamProtocol.pack_qstring(str(i)) for i in range(1520)])))
    reader.feed_eof()
    message = yield from protocol.read_message()

    assert message == {'legacy': [str(i) for i in range(1520)]}


def test_QDataStreamProtocol_send_equality_reference():
    test = '{some_json: true}'
    assert QDataStreamProtocol.pack_message('{some_json: true}') == preparePacket(test)


def test_QDataStreamProtocol_send_equality_reference_legacy():
    args = ['{some_json: true}', 'login', '123']
    assert QDataStreamProtocol.pack_message(*args) == preparePacket('{some_json: true}', 'login', '123')
