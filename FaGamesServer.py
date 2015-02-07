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


from PySide.QtNetwork import QTcpServer, QTcpSocket
import logging
from gameconnection import GameConnection

class FAServer(QTcpServer):
    def __init__(self, loop, listUsers, Games, db, dirtyGameList, parent=None):
        super(FAServer, self).__init__(parent)
        self.loop = loop
        self.parent = parent
        self.logger = logging.getLogger(__name__)
        self.sockets = {}
        self.logger.debug("Starting FAServer")
        self.dirtyGameList = dirtyGameList
        self.listUsers = listUsers
        self.games = Games
        self.db = db
        self.recorders = []

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
        self.close()

    def clean_socket(self, socket):
        """
        :type socket QTcpSocket
        """
        if socket.isOpen():
            socket.abort()

    def incomingConnection(self, socket_id):
        self.logger.debug("Incoming Game Connection")

        socket = QTcpSocket()
        if socket.setSocketDescriptor(socket_id):
            self.sockets[socket_id] = socket
            connection = GameConnection(self.loop, self.listUsers, self.games, self.db, self)
            connection.accept(socket)
            self.recorders.append(connection)

    def removeRecorder(self, recorder):
        if recorder in self.recorders:
            self.recorders.remove(recorder)
            recorder.deleteLater()

    def addDirtyGame(self, game):
        if not game in self.dirtyGameList:
            self.dirtyGameList.append(game)

