#!/usr/bin/env python

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


from PySide.QtCore import QThread, QObject, SIGNAL, SLOT
from PySide.QtCore import QByteArray, QDataStream, QIODevice, QReadWriteLock
from PySide.QtNetwork import QTcpServer, QTcpSocket, QAbstractSocket, QHostInfo
  
from PySide import QtCore, QtNetwork, QtSql
from PySide.QtSql import *

import uuid
import random
import logging

from passwords import DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_TABLE


from replays.replayServer import *

UNIT16 = 8

class start(QObject):

    def __init__(self, parent=None):

        super(start, self).__init__(parent)
        self.logger = logging.getLogger('FAReplayServer')

        self.db= QtSql.QSqlDatabase.addDatabase("QMYSQL")  
        self.db.setHostName(DB_SERVER)  
        self.db.setPort(DB_PORT)

        self.db.setDatabaseName(DB_TABLE)  
        self.db.setUserName(DB_LOGIN)  
        self.db.setPassword(DB_PASSWORD)
        

        
        if not self.db.open():  
            self.logger.error(self.db.lastError().text())  
 
        
        self.updater =  replayServer(self)
        if not self.updater.listen(QtNetwork.QHostAddress.Any, 11002):
            return        
        else:
            self.logger.info ("starting the replay server on  %s:%i" % (self.updater.serverAddress().toString(),self.updater.serverPort()))  




logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    datefmt='%m-%d %H:%M'
    )
x = logging.getLogger("FAServerUpdater")
x.setLevel(logging.DEBUG)

h = logging.StreamHandler()

x.addHandler(h)
h1 = logging.FileHandler("debugReplay.log")

h1.setLevel(logging.DEBUG)
x.addHandler(h1)


if __name__ == '__main__':
    logger = logging.getLogger("FAServerTournament")
    import sys
    

    try:
        
        app = QtCore.QCoreApplication(sys.argv)
        server = start()
        app.exec_()
    
    except Exception, ex:
        
        logger.exception("Something awful happened!")
        logger.debug("Finishing main")

