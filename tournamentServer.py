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
from logging import handlers

from passwords import DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_TABLE
from configobj import ConfigObj
config = ConfigObj("/etc/faforever/faforever.conf")

from tournament.tournamentServer import *

UNIT16 = 8

class start(QObject):

    def __init__(self, parent=None):

        super(start, self).__init__(parent)
        self.rootlogger = logging.getLogger("")
        self.logHandler = handlers.RotatingFileHandler(config['global']['logpath'] + "tournamentServer.log", backupCount=15, maxBytes=524288 )
        self.logFormatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s')
        self.logHandler.setFormatter( self.logFormatter )
        self.rootlogger.addHandler( self.logHandler )
        self.rootlogger.setLevel( eval ("logging." + config['tournamentServer']['loglevel'] ))
        self.logger = logging.getLogger(__name__)

        self.db= QtSql.QSqlDatabase.addDatabase("QMYSQL")  
        self.db.setHostName(DB_SERVER)  
        self.db.setPort(DB_PORT)

        self.db.setDatabaseName(DB_TABLE)  
        self.db.setUserName(DB_LOGIN)  
        self.db.setPassword(DB_PASSWORD)
        

        
        if not self.db.open():  
            self.logger.error(self.db.lastError().text())  
 
        
        self.updater =  tournamentServer(self)
        if not self.updater.listen(QtNetwork.QHostAddress.Any, 11001):
            return        
        else:
            self.logger.info ("starting the update server on  %s:%i" % (self.updater.serverAddress().toString(),self.updater.serverPort()))  

if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    import sys
    

    try:
        
        app = QtCore.QCoreApplication(sys.argv)
        server = start()
        app.exec_()
    
    except Exception, ex:
        
        logger.exception("Something awful happened!")
        logger.debug("Finishing main")

