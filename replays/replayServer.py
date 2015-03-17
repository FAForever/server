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

import logging

from PySide import QtNetwork
from PySide.QtSql import *


UNIT16 = 8

from . import replayServerThread


class replayServer(QtNetwork.QTcpServer):
    def __init__(self, parent=None):
        super(replayServer, self).__init__(parent)
        self.logger = logging.getLogger(__name__)

        self.parent = parent
        self.db = self.parent.db
        self.replayVault = []

        self.mods = {}
        self.getMods()
        
    def getMods(self):
        query = QSqlQuery(self.parent.db)
        query.setForwardOnly(True)
        query.prepare("SELECT id, gamemod FROM `game_featuredMods` WHERE 1")
        query.exec_()
        if query.size() != 0 : 
            while next(query):
                uid = int(query.value(0))
                name = str(query.value(1))
                if not uid in self.mods :
                    self.mods[uid] = name       

    def incomingConnection(self, socketId):
        
        reload(replayServerThread)
        self.logger.debug("Incoming replay Connection")
        self.replayVault.append(replayServerThread.replayServerThread(socketId, self))    
    
    def removeUpdater(self, updater):
        if updater in self.replayVault:
            self.replayVault.remove(updater)
            updater.deleteLater()    
