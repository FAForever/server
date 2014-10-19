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

from PySide import QtCore, QtNetwork, QtSql
from types import IntType, FloatType, ListType, DictType, LongType

SERVER_PORT = 10001

import json
import sys
import time
import os
import logging
import pickle
import base64

from passwords import DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_TABLE

CREDITTIMER = 1000 * 60 * 60 * 6

class ServerMain(QtCore.QObject):
    '''
    This is the main server that manages the connection of clients, and dispatch them to the correct module'''
    
    def __init__(self, parent=None, *args, **kwargs):
        
        super(ServerMain, self).__init__(parent) 
        
        self.log = logging.getLogger(__name__)
        
        self.log.debug("Server instantiating")
        
        # Hook to Qt's application management system
        QtCore.QCoreApplication.instance().aboutToQuit.connect(self.cleanup)
        
        
        #Database thingys
        self.db= QtSql.QSqlDatabase.addDatabase("QMYSQL")  
        self.db.setHostName(DB_SERVER)  
        self.db.setPort(DB_PORT)

        self.db.setDatabaseName(DB_TABLE)  
        self.db.setUserName(DB_LOGIN)  
        self.db.setPassword(DB_PASSWORD)
        
        self.db.setConnectOptions("MYSQL_OPT_RECONNECT = 1")

        self.mainServer = QtNetwork.QTcpSocket()
        self.mainServer.readyRead.connect(self.readFromServer)
        self.mainServer.disconnected.connect(self.disconnectedFromServer)
        self.mainServer.error.connect(self.socketError)        

        self.blockSize = 0
        self.listUsers = {}
        
        self.mainServer.connectToHost(QtNetwork.QHostAddress.LocalHost, 8002)

        while (self.mainServer.state() != QtNetwork.QAbstractSocket.ConnectedState) :
            QtCore.QCoreApplication.processEvents()
            self.log.debug("connecting to server ...")
                 
      
            
        self.sessions = []    
        #self.askPlayerList(0)
                    
        if not self.db.open():  
            self.log.error(self.db.lastError().text())  
            
                
        self.timoutTimer = QtCore.QTimer(self)
        self.timoutTimer.timeout.connect(self.antiTimeout) 
        self.timoutTimer.start(300000)

        
        
        self.creditTimer = QtCore.QTimer(self)
        self.creditTimer.timeout.connect(self.generatingCredits) 
        self.creditTimer.start(CREDITTIMER) 
        
        self.cleanAttacks()
        
    def cleanAttacks(self):
        query = QtSql.QSqlQuery(self.db)
        query.prepare("DELETE FROM attacks WHERE defended = 1")
        query.exec_() 
 
    def generatingCredits(self):
        try :
            self.log.info("Generating credits")
            #first we get all the players active. An active player played a game in the last seven day.
            activePlayers = 0
            query = QtSql.QSqlQuery(self.db)
            query.prepare("SELECT COUNT(`uid`) FROM `avatars` WHERE `alive` = 1 AND `lastPlayed` > SUBDATE( NOW( ) , 7 )")
            query.exec_()
            if query.size() == 1 :
                query.first()
                activePlayers = int(query.value(0))
            
            # then we generate 300 credits per player
            credits = 300 * activePlayers
            
            # Each faction will received 1/4th of the credits 
            credits = int(credits / 4)
            
            self.log.info("Generating " + str(credits) + " per faction")
            # Now, we give that amount to each active per faction
            factions = ["uef", "aeon", "cybran", "seraphim"]
            for i in xrange(0,4) :
                
                query = QtSql.QSqlQuery(self.db)
                sc = 0
                fc = 0
                query.prepare("SELECT ROUND(?/COUNT(*)) FROM `avatars` LEFT JOIN accounts ON avatars.`uid` = accounts.uid WHERE `alive` = 1 AND `lastPlayed` > SUBDATE( NOW( ) , 7 ) AND faction = ?")
                query.addBindValue(credits)
                query.addBindValue(i)
                query.exec_()
                self.log.debug(query.lastQuery())
                if query.size() == 1 :
                    query.first()
                    if query.value(0) != None :
                        sc = int(query.value(0)) 
                        #that's the base.
                
                # Now the credits depending of planets.
                query.prepare("SELECT COUNT(*), SUM(`%s`) FROM `planets` WHERE 1;" % factions[i])
                query.exec_()
                if query.size() == 1:
                    query.first()
                    tp = float(query.value(0))
                    fp = float(query.value(1))
                    if tp == 0:
                        tp = 0.01
                    
                    fc = int(sc * (1.2 + (fp/tp)) * 5/6)
                
                self.log.info("Generating " + str(fc) + " per player for faction " + str(i))
                query = QtSql.QSqlQuery(self.db)
                query.prepare("UPDATE `avatars` LEFT JOIN accounts ON avatars.`uid` = accounts.uid SET `credits`= LEAST(credits+?, 1000+`rank`*1000) WHERE `alive` = 1 AND `lastPlayed` > SUBDATE( NOW( ) , 7 ) AND faction = ? AND ((1000+`rank`*1000) >= LEAST(credits+?,1000+`rank`*1000))")                        
                query.addBindValue(fc)
                query.addBindValue(i)
                query.addBindValue(fc)
                query.exec_()
            
     
            # The credits are generated, we need to update all the players.
            if self.gwServer :
                self.gwServer.updateAllPlayers()
        except :
            self.log.exception("Something awful happened while generating money !")
            
            
    
 
    def askPlayer(self, login, session = 0):
        self.sessions.append(session)
        self.send(dict(command="request", action="player_info", login = login, session = session))

 
    def antiTimeout(self):
        query = QtSql.QSqlQuery(self.db)
        queryStr = 'SELECT "KEEP ALIVE";'
        query.exec_(queryStr)
        
    
    def readFromServer(self):
        try :
            ins = QtCore.QDataStream(self.mainServer)        
            ins.setVersion(QtCore.QDataStream.Qt_4_2)
            
            while ins.atEnd() == False :
                if self.blockSize == 0:
                    if self.mainServer.bytesAvailable() < 4:
                        return
                    self.blockSize = ins.readUInt32()            
                if self.mainServer.bytesAvailable() < self.blockSize:
                    return
                
                action = ins.readQString()
                self.process(action, ins)
                self.blockSize = 0
        except :
            self.log.exception("Something awful happened in a gw thread !")
    
    def process(self, action, stream):
        if action == "ACK":
            pass
        
        elif action == "PING":
            self.writeToServer("PONG")
        else :
            self.receiveJSON(action, stream)
            
    
    def command_autorecall(self, message):
        self.gwServer.autorecall(message)
    
    def command_attack(self, message):
        self.gwServer.playerAttackCheck(message)
    
    def command_results(self, message):
        self.gwServer.attackResult(message)
        
    def command_delete_group(self, message):
        self.gwServer.delete_group(message)
        
    def command_game_info(self, message):
        self.gwServer.gameInfo(message)

    def command_game(self, message):
        state = message["state"]
        if not "gameuid" in message:
            return
        if not "planetuid" in message:
            return
            
        planetuid = message["planetuid"]
        gameuuid = message["gameuid"]
        if state =="started" :
            self.gwServer.attackStarted(planetuid, gameuuid)
        elif state == "aborted" :
            self.gwServer.gameAborted(planetuid)       
        elif state == "hosted" :
            self.gwServer.gameHosted(planetuid)
        elif state == "left" :
            playeruid = message["playeruid"]
            self.gwServer.playerHasLeft(planetuid, playeruid)
        elif state == "player_join":
            playeruid = message["playeruid"]
            self.gwServer.playerHasJoin(planetuid, playeruid)
    
    def command_player_info(self, message):
        login   = message["login"]
        uid     = int(message["uid"])
        session = message["playersession"]

        self.log.debug("adding user %s" % login)
        self.listUsers[uid] = dict(login=login, uid=uid, session=session)
        self.sessions.remove(message["session"])
    
    def command_update(self, message):
        action = message["action"]
        if action == "players_list" :
            self.listUsers = message["data"]
            if message["session"] in self.sessions :
                self.sessions.remove(message["session"])

    
    def receiveJSON(self, data_string, stream):
        '''
        A fairly pythonic way to process received strings as JSON messages.
        '''
        try :
            message = json.loads(data_string)
        except :
            self.log.error(data_string)

        cmd = "command_" + message['command']
        self.log.debug("receive JSON command %s" %cmd)
        if hasattr(self, cmd):
            getattr(self, cmd)(message) 

    def send(self, message):
        data = json.dumps(message)
        self.log.info("Outgoing JSON Message: " + data)
        self.sendReply(data)
        
        


    def sendReply(self, action, *args, **kwargs) :
        
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
            elif isinstance(arg, basestring):                       
                stream.writeQString(arg)                  
            elif type(arg) is StringType  :
                stream.writeQString(arg)
            elif type(arg) is FloatType:
                stream.writeFloat(arg)
            elif type(arg) is ListType:
                stream.writeQString(str(arg))
    
        stream.device().seek(0)
        
        stream.writeUInt32(reply.size() - 4)

        if self.mainServer.write(reply) != -1 :
            self.log.debug("message sent")
        else :
            self.log.warn("error when sending message")
   
    def disconnectedFromServer(self):
        pass
    
    def socketError(self):
        pass
    
    def setup(self):
        import gwServer
       
        self.gwServer = gwServer.gwServer(self.db, self)
        
        if not self.gwServer.listen(QtNetwork.QHostAddress.Any, SERVER_PORT):
            self.log.error ("Unable to start the server")
            raise Exception("Unable to start the lobby server")
            
        else:
            self.log.info("starting the server on  %s:%i" % (self.gwServer.serverAddress().toString(),self.gwServer.serverPort()))        
    
    def cleanup(self):
        '''
        Perform cleanup before the server closes
        '''        
        self.db.close()
        self.mainServer.close()


            
