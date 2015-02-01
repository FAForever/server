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
import FAGamesServerThread

class FAServer(QTcpServer):
    def __init__(self, listUsers, Games, db,  dirtyGameList, parent=None):
        super(FAServer, self).__init__(parent)
        self.parent = parent
        self.logger = logging.getLogger(__name__)

        self.logger.debug("initializing server")
        self.dirtyGameList = dirtyGameList
        self.listUsers = listUsers
        self.games = Games
        self.db = db
        self.recorders = []


    def incomingConnection(self, socket_id):
        self.logger.debug("Incoming Game Connection")
        socket = QTcpSocket()

        if socket.setSocketDescriptor(socket_id):
            self.recorders.append(FAGamesServerThread.FAGameThread(socket, self))
    

    def removeRecorder(self, recorder):
        if recorder in self.recorders:
            self.recorders.remove(recorder)
            recorder.deleteLater()

    def addDirtyGame(self, game):
        if not game in self.dirtyGameList:
            self.dirtyGameList.append(game)
