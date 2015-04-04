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


import operator
import logging
import json

from PySide.QtCore import QObject
from PySide.QtCore import QByteArray, QDataStream, QIODevice, QFile, QCoreApplication
from PySide import QtCore, QtNetwork
from PySide.QtSql import *

import challonge
from passwords import CHALLONGE_KEY, CHALLONGE_USER


class tournamentServerThread(QObject):
    """
    FA server thread spawned upon every incoming connection to
    prevent collisions.
    """
    def __init__(self, socketId, parent=None):
        super(tournamentServerThread, self).__init__(parent)

        self.log = logging.getLogger(__name__)


        self.app = None
        
        challonge.set_credentials(CHALLONGE_USER, CHALLONGE_KEY)
        
        self.socket = QtNetwork.QTcpSocket(self)
        self.socket.setSocketDescriptor(socketId)
        self.parent = parent
        
        if self.socket.state() == 3 and self.socket.isValid():
            
            self.nextBlockSize = 0
    
            self.blockSize = 0   

            self.socket.readyRead.connect(self.readDatas)
            self.socket.disconnected.connect(self.disconnection)

            self.parent.db.open()   
            self.pingTimer = QtCore.QTimer(self)
            self.pingTimer.start(31000)
            self.pingTimer.timeout.connect(self.ping)
            
    def ping(self):
        self.sendJSON(dict(command="ping"))
        
    def command_pong(self, message):
        return
    
    def command_add_participant(self, message):
        uid     = message["uid"]
        login   = message["login"] 
        
        challonge.participants.create(uid,login)
        
        participants = challonge.participants.index(uid)
        query = QSqlQuery(self.parent.db)
        seeding = {}
        for p in participants:
            query.prepare("SELECT (mean-3*deviation) FROM global_rating WHERE id = (SELECT id FROM login WHERE login = ?)")
            query.addBindValue(p["name"])
            rating = 0
            if query.exec_():
                if query.size() == 1:
                    query.first()
                    rating = float(query.value(0))
            
            seeding[p["id"]] = rating
            
        sortedSeed = sorted(iter(seeding.items()), key=operator.itemgetter(1), reverse=True)

        for i in range(len(sortedSeed)):
            challonge.participants.update(uid, sortedSeed[i][0], seed=str(i+1))

        self.log.debug("player added, reloading data")
        self.parent.importTournaments()
        

        self.log.debug("sending ata")
        self.sendJSON(dict(command="tournaments_info", data=self.parent.tournaments))
            
    
    def command_remove_participant(self, message):
        uid = message["uid"]
        login = message["login"] 
        
        participants = self.parent.tournaments[uid]["participants"]
        for p in participants:
            if p["name"] == login:
                challonge.participants.destroy(uid, p["id"])
        self.parent.importTournaments()
        self.sendJSON(dict(command="tournaments_info", data=self.parent.tournaments)) 
        # for conn in self.parent.updaters:
        #     conn.sendJSON(dict(command="tournaments_info", data=self.parent.tournaments))        
                
    
    def command_get_tournaments(self, message):
        self.sendJSON(dict(command="tournaments_info", data=self.parent.tournaments))
        
    
    def handleAction(self, action, stream):
        self.receiveJSON(action, stream)
        return 1


    def readDatas(self):
        if self.socket is not None:
            if self.socket.isValid():
                ins = QDataStream(self.socket)
                ins.setVersion(QDataStream.Qt_4_2)
                loop = 0
                while not ins.atEnd():
                    QCoreApplication.processEvents()
                    loop += 1
                    if self.socket is not None:
                        if self.socket.isValid():
                            if self.blockSize == 0:
                                if self.socket.isValid():
                                    if self.socket.bytesAvailable() < 4:
                                        return
                                    self.blockSize = ins.readUInt32()
                                else:
                                    return
                            if not self.socket.isValid():
                                return  
                            action = ins.readQString()
                            self.handleAction(action, ins)
                            self.blockSize = 0
                        else: 
                            return    
                    else:
                        return
                return


    def disconnection(self):
        self.done()


    def sendJSON(self, data_dictionary):
        """
        Simply dumps a dictionary into a string and feeds it into the QTCPSocket
        """
        try:
            data_string = json.dumps(data_dictionary)
            self.sendReply(data_string)
        except:
            self.log.warning("wrong data")
            self.socket.abort()
            return


    def receiveJSON(self, data_string, stream):
        """
        A fairly pythonic way to process received strings as JSON messages.
        """
        try:
            message = json.loads(data_string)

            cmd = "command_" + message['command']
            if hasattr(self, cmd):
                getattr(self, cmd)(message)  
        except:
            self.log.warning("command error")
            self.socket.abort()
            return


    def sendReply(self, action, *args, **kwargs):
        try:
            if hasattr(self, "socket"):
                reply = QByteArray()
                stream = QDataStream(reply, QIODevice.WriteOnly)
                stream.setVersion(QDataStream.Qt_4_2)
                stream.writeUInt32(0)
                
                stream.writeQString(action)

                for arg in args:
                    if type(arg) is LongType:
                        stream.writeQString(str(arg))
                    if type(arg) is IntType:
                        stream.writeInt(int(arg))
                    elif type(arg) is StringType:
                        stream.writeQString(arg)
                    elif isinstance(arg, str):                       
                        stream.writeQString(arg) 
                    elif type(arg) is FloatType:
                        stream.writeFloat(arg)
                    elif type(arg) is ListType:
                        stream.writeQString(str(arg))                        
                    elif type(arg) is QFile:
                        arg.open(QIODevice.ReadOnly)
                        fileDatas = QByteArray(arg.readAll())
                        stream.writeInt32(fileDatas.size())
                        stream.writeRawData(fileDatas.data())
                        arg.close()                        
                #stream << action << options
                stream.device().seek(0)
                
                stream.writeUInt32(reply.size() - 4)
                if self.socket:
                    self.socket.write(reply)


        except:
                self.log.exception("Something awful happened when sending reply !")  


    def done(self):
        self.parent.removeUpdater(self)
        if self.socket:
            self.socket.deleteLater()
