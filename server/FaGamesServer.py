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

from PySide.QtNetwork import QTcpServer, QTcpSocket

from server.gameconnection import GameConnection
import config
from server.games_service import GamesService
from server.natpacketserver import NatPacketServer
from server.decorators import with_logger


@with_logger
class FAServer(QTcpServer):
    def __init__(self, loop, listUsers, games: GamesService, db, parent=None):
        QTcpServer.__init__(self, parent)
        self.loop = loop
        self.sockets = {}
        self._logger.debug("Starting FAServer")
        self.nat_packet_server = NatPacketServer(loop, config.LOBBY_UDP_PORT)
        self.nat_packet_server.subscribe(self, ['ProcessServerNatPacket'])
        self.newConnection.connect(self._on_new_connection)
        self.listUsers = listUsers
        self.games = games
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
        self.nat_packet_server.__exit__(exc_type, exc_val, exc_tb)
        self.close()

    def clean_socket(self, socket: QTcpSocket):
        if socket.isOpen():
            socket.abort()

    def run(self, address):
        self._logger.debug("Server listening on {}:{}".format(address, 8000))
        return self.listen(address, 8000)

    def handle_ProcessServerNatPacket(self, arguments):
        """
        FIXME: This is rather inefficient, need to implement progagation of subscriptions
        :param arguments:
        :return:
        """
        for connection in self.connections:
            connection.notify(dict(command_id='ProcessServerNatPacket', arguments=arguments))

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
