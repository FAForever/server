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

from PySide import QtCore, QtNetwork

import logging
import json
import time

import GWServerThread

logger = logging.getLogger(__name__)

class GWLobbyServer(QtNetwork.QTcpServer):
    def __init__(self, listUsers, Games, db, dirtyGameList, parent=None):
        super(GWLobbyServer, self).__init__(parent)
        
        self.parent = parent
        self.logger = logging.getLogger(__name__)

        self.logger.debug("Starting GW server")

        
        self.dirtyGameList = dirtyGameList
        self.listUsers = listUsers
        self.games = Games

        self.db = db
        self.recorders = []
        self.socketToDelete = []

    
    def incomingConnection(self, socketId):
        self.logger.debug("incoming GW server")
        reload(GWServerThread)
        self.recorders.append(GWServerThread.GWServerThread(socketId, self))    


    def removeRecorder(self, recorder):
        if recorder in self.recorders:
            self.recorders.remove(recorder)
            recorder.deleteLater()

    def preparePacket(self, action, *args, **kwargs) :
        reply = QtCore.QByteArray()
        stream = QtCore.QDataStream(reply, QtCore.QIODevice.WriteOnly)
        stream.setVersion(QtCore.QDataStream.Qt_4_2)
        stream.writeUInt32(0)
        
        stream.writeQString(action)
        
        for arg in args :
            if type(arg) is LongType :
                stream.writeQString(str(arg))
            elif type(arg) is IntType:
                stream.writeInt(arg)
            elif isinstance(arg, str):                       
                stream.writeQString(arg)                  
            elif type(arg) is StringType  :
                stream.writeQString(arg)
            elif type(arg) is FloatType:
                stream.writeFloat(arg)
            elif type(arg) is ListType:
                stream.writeQString(str(arg))
        
        stream.device().seek(0)
        
        stream.writeUInt32(reply.size() - 4)  
        
        return reply  

    def prepareBigJSON(self, data_dictionary):
        '''
        Simply dumps a dictionary into a string and feeds it into the QTCPSocket
        '''

        data_string = ""
        try :
            data_string = json.dumps(data_dictionary)
        except :
            return

        return self.preparePacket(data_string)
    

    def addSocketToDelete(self, socket):     
        self.socketToDelete.append([time.time(), socket])
            


