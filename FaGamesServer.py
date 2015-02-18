#-------------------------------------------------------------------------------
# Copyright (c) 2014 Gael Honorez.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#-------------------------------------------------------------------------------
import asyncio
from asyncio.base_events import BaseEventLoop
import socket

from PySide.QtCore import QObject, Signal, Slot
from PySide.QtNetwork import QTcpServer, QTcpSocket

from src.gameconnection import GameConnection
import config
from src.with_logger import with_logger


@with_logger
class NatPacketServer(QObject):
    datagram_received = Signal(str, str, int)
    def __init__(self, loop: BaseEventLoop, port, parent=None):
        QObject.__init__(self, None)
        self.loop = loop
        self.port = port
        self._logger.debug("{id} Listening on {port}".format(id=id(self), port=port))
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', port))
        loop.add_reader(s.fileno(), self._on_psocket_data)
        self._psocket = s
        self._subscribers = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._socket.abort()

    def _on_psocket_data(self):
        data, addr = self._psocket.recvfrom(512)
        self._logger.debug("Received UDP from {}: {}".format(addr, data))
        if data[0] == 8:
            self._logger.debug("Emitting with: {} {} {} ".format(data[1:].decode(), addr[0], addr[1]))
            self.datagram_received.emit(data[1:].decode(), addr[0], addr[1])

    def _on_error(self):
        self._logger.critical("Socket error {}".format(self._socket.errorString()))

    def _on_ready_data(self):
        self._logger.debug("On_ready_data called {}".format(id(self)))
        while self._socket.hasPendingDatagrams():
            self._logger.debug("HasPendingDatagrams: {}".format(self._socket.hasPendingDatagrams()))
            data, host, port = self._socket.readDatagram(self._socket.pendingDatagramSize())
            if data[0] == b'\x08':  # GPG NAT packets start with this byte
                self._logger.debug("Emitting datagram_received {}".format(data))
                # Doing anything interesting with data
                # will apparently cause a full deep copy
                # of all objects the signal
                # gets propagated to.
                # We don't want that.
                self.datagram_received.emit("{}".format(data), host.toString(), port)


    def _on_ready_read(self):
        while self._socket.hasPendingDatagrams():
            data, host, port = self._socket.readDatagram(self._socket.pendingDatagramSize())
            self._logger.debug('Received {data} from {host}:{port}'.format(data=data, host=host, port=port))
            self._logger.debug("First bit: {}".format(data[0]))
            if data[0] == b'\x08':  # GPG NAT packets start with this byte
                self._logger.debug("Emitting datagram_received")
                # Doing anything interesting with data
                # will apparently cause a full deep copy
                # of all objects the signal
                # gets propagated to.
                # We don't want that.
                self.datagram_received.emit("{}".format(data), host.toString(), port)

@with_logger
class FAServer(QTcpServer):
    def __init__(self, loop, listUsers, Games, db, dirtyGameList, parent=None):
        QTcpServer.__init__(self, parent)
        self.loop = loop
        self.sockets = {}
        self._logger.debug("Starting FAServer")
        self.nat_packet_server = NatPacketServer(loop, config.LOBBY_UDP_PORT, self)
        self.nat_packet_server.datagram_received.connect(self._on_nat_packet)
        self.newConnection.connect(self._on_new_connection)
        self.dirtyGameList = dirtyGameList
        self.listUsers = listUsers
        self.games = Games
        self.db = db
        self.done = asyncio.Future()
        self.connections = []

    def __enter__(self):
        """
        Allows using the FAServer object as a context manager
        :return: FAServer
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Abort any excess open sockets and shut down the server
        :param exc_type:
        :param exc_val:
        :param exc_tb:
        :return:
        """
        for socket_id, socket in self.sockets.items():
            self.clean_socket(socket)
        self.done.set_result(True)
        self.close()

    def clean_socket(self, socket: QTcpSocket):
        if socket.isOpen():
            socket.abort()

    def run(self, address):
        self._logger.debug("Server listening on {}:{}".format(address, 8000))
        return self.listen(address, 8000)

    @Slot(str, str, int)
    def _on_nat_packet(self, data, host, port):
        self._logger.debug("NAT PACKET: {} {} {}".format(data, host, port))
        for connection in self.connections:
            self._logger.debug("Propagating to {}".format(id(connection)))
            connection.handle_ProcessServerNatPacket(data, host, port)

    def _on_new_connection(self):
        self._logger.debug("New connection")
        if self.hasPendingConnections():
            socket = self.nextPendingConnection()
            self.sockets[socket.socketDescriptor()] = socket
            connection = GameConnection(self.loop, self.listUsers, self.games, self.db, self)
            connection.accept(socket)
            self.connections.append(connection)

    def removeRecorder(self, recorder):
        if recorder in self.connections:
            self.connections.remove(recorder)
            recorder.deleteLater()

    def addDirtyGame(self, game):
        if not game in self.dirtyGameList:
            self.dirtyGameList.append(game)

