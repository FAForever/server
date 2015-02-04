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

from PySide.QtCore import QByteArray, QDataStream, QIODevice, SIGNAL, SLOT, QReadWriteLock, QReadLocker
from PySide.QtNetwork import QTcpServer, QTcpSocket, QAbstractSocket, QHostInfo
  
from PySide import QtCore, QtGui, QtNetwork, QtSql
from PySide.QtSql import *

import uuid
import random
import logging
import time


from . import updateServerThread
from . import createPatch
import psutil
import pprint

class updateServer(QtNetwork.QTcpServer):
    def __init__(self, parent=None):
        super(updateServer, self).__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.parent = parent
        self.threads = []
        self.db = self.parent.db
        self.updaters = []
        self.patching = False


        
    def incomingConnection(self, socketId):
        
        reload(updateServerThread)
        self.updaters.append(updateServerThread.updateServerThread(socketId, self))    

    def createPatch(self, patches):

        if self.patching == False:
            reload(createPatch)
            self.patching = True
            self.logger.debug(patches)
            thread = createPatch.createPatch(patches, self.db)

            self.connect(thread, SIGNAL("finished()"),thread, SLOT("deleteLater()"))
            
            thread.finished.connect(self.done)     
            thread.start()
            self.threads.append(thread)
            self.logger.debug("starting patch creation")
  

        
    def removeUpdater(self, updater):
        if updater in self.updaters:
            self.updaters.remove(updater)
            updater.deleteLater()
        
        
    def done(self):
        self.logger.debug("thread done")
        
        for thread in self.threads :
            if thread:
                self.threads.remove(thread)
                try:
                    if thread.isRunning() == False :
                        thread.done()
                        if thread.isFinished() :
                            self.patching = False
                            del thread
                except:
                    pass
