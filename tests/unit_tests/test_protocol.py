from unittest import mock
from unittest.mock import call
from PySide.QtCore import QByteArray, QDataStream, QIODevice
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


def test_QDataStreamProtocol_recv_small_message():
    protocol = QDataStreamProtocol()
    protocol.on_message_received = mock.Mock()

    protocol.data_received(QDataStreamProtocol.pack_block(b''.join(
                                                        [QDataStreamProtocol.pack_qstring('Hello'),
                                                         QDataStreamProtocol.pack_qstring('Goodbye')])))

    assert protocol.on_message_received.mock_calls == [call('Hello'), call('Goodbye')]


def test_QDataStreamProtocol_recv_malformed_message():
    protocol = QDataStreamProtocol()
    protocol.on_message_received = mock.Mock()
    protocol._transport = mock.Mock()

    protocol.data_received(QDataStreamProtocol.pack_block(b'\0\0absatars'))

    assert protocol.on_message_received.mock_calls == []
    protocol._transport.write_eof.assert_called_with()


def test_QDataStreamProtocol_recv_large_array():
    protocol = QDataStreamProtocol()
    protocol.on_message_received = mock.Mock()

    block = QDataStreamProtocol.pack_block(b''.join([QDataStreamProtocol.pack_qstring(str(i)) for i in range(1520)]))
    protocol.data_received(block)

    assert protocol.on_message_received.mock_calls == [call(str(i)) for i in range(1520)]


def test_QDataStreamProtocol_send_equality_reference():
    protocol = QDataStreamProtocol()
    protocol._transport = mock.Mock()

    protocol.send_message('{some_json: true}')

    expected_bytes = preparePacket('{some_json: true}')
    protocol._transport.write.assert_called_with(expected_bytes)


def test_QDataStreamProtocol_send_equality_reference_legacy():
    protocol = QDataStreamProtocol()
    protocol._transport = mock.Mock()

    protocol.send_legacy('{some_json: true}', 'login', '123')

    expected_bytes = preparePacket('{some_json: true}', 'login', '123')
    protocol._transport.write.assert_called_with(expected_bytes)
