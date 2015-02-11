import struct

import json
import logging
from PySide import QtCore
from PySide.QtCore import QObject


class Transport(QObject):
    messageReceived = QtCore.Signal(str)
    writeFailed = QtCore.Signal(str)

    def __init__(self, socket):
        super(Transport, self).__init__()
        self.socket = socket
        self.logger = logging.getLogger(__name__)

    def _on_message(self, msg):
        self.logger.debug("<< %r" % msg)
        self.messageReceived.emit(msg)

    def _onWriteFailed(self):
        self.logger.warn("Write failed")
        self.writeFailed.emit(self.socket.errorString())
        pass

    def send_message(self, msg):
        self.logger.debug(">> %r" % msg)
        self._send(msg)


class JsonTransport(Transport):
    def __init__(self, socket):
        super(JsonTransport, self).__init__(socket)
        self.socket.readyRead.connect(self._onReadyRead)

    def _on_ready_read(self):
        while self.socket.bytesAvailable() >= 4:
            size, _ = struct.unpack('=l', self.socket.peek(4))

            if self.socket.bytesAvailable() < size + 4:
                return

            self.socket.read(4)
            msg = json.loads(self.socket.read(size).decode())
            self._on_message(msg)

    def _send(self, msg):
        data = json.dumps(msg).encode()
        self.socket.write(struct.pack('=l', len(data)))
        self.socket.write(data)


class QDataStreamJsonTransport(Transport):
    def __init__(self, socket):
        super(QDataStreamJsonTransport, self).__init__(socket)
        self.socket = socket
        self.noSocket = False
        socket.readyRead.connect(self._on_ready_read)

    def _on_ready_read(self):
        if self.socket.isValid():
            if self.socket.bytesAvailable() == 0:
                return
            ins = QtCore.QDataStream(self.socket)
            ins.setVersion(QtCore.QDataStream.Qt_4_2)
            while not ins.atEnd():
                    if self.socket.bytesAvailable() < 4:
                        return
                    block_size = ins.readUInt32()

                    if self.socket.bytesAvailable() < block_size:
                        return

                    message = ins.readQString()

                    self._on_message(message)
            return

    def _send(self, message):
        block = QtCore.QByteArray()
        out = QtCore.QDataStream(block, QtCore.QIODevice.ReadWrite)
        out.setVersion(QtCore.QDataStream.Qt_4_2)

        out.writeUInt32(0)
        out.writeQString(json.dumps(message))

        out.device().seek(0)
        out.writeUInt32(block.size() - 4)

        if self.socket.write(block) == -1:
            self._onWriteFailed()
