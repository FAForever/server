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


from PySide.QtCore import SIGNAL, SLOT, QTimer
from PySide.QtCore import QByteArray, QDataStream, QIODevice, QFile, QCoreApplication, QObject

from types import IntType, FloatType, ListType, DictType, LongType  

from PySide import QtCore, QtNetwork
from PySide.QtSql import QSqlQuery

import base64, zlib
import urllib

from players import *


import json
import logging
import pickle
import time

logger = logging.getLogger(__name__)

try :
    import gameModes.gwContainer
    reload(gameModes.gwContainer)   
    from gameModes.gwContainer import gwGamesContainerClass
except :
    self.log.exception("Something awful happened trying to put that thing!")


from functools import wraps


def timed(f):
  @wraps(f)
  def wrapper(*args, **kwds):
    start = time.time()
    result = f(*args, **kwds)
    elapsed = time.time() - start
    if elapsed > 1 :
        logger.info("%s took %s time to finish" % (f.__name__, str(elapsed)))
    return result
  return wrapper


class GWServerThread(QObject):
    @timed
    def __init__(self, socket, parent=None):
        super(GWServerThread, self).__init__(parent)
        self.parent = parent
        
        self.log = logging.getLogger(__name__)
        
        self.log.debug("Incoming GW server socket started")
        self.socket = None
        self.socket = QtNetwork.QTcpSocket(self)
        
        if self.socket.setSocketDescriptor(socket) == False :
            self.log.debug("awful error : Socket descriptor not set")
            self.socket.abort()
            return
  

        self.socket.readyRead.connect(self.readDatas)
        self.socket.disconnected.connect(self.disconnection)
        self.socket.error.connect(self.displayError)    
        self.socket.stateChanged.connect(self.stateChange)
        
        self.blockSize = 0
        
        try :
            if not self.parent.games.isaContainer("gw"):
                self.parent.games.addContainer("gw", gwGamesContainerClass(self.parent.db, self.parent.games))
            
            self.parent.games.reloadContainer("gw", force = True)
        except :
            self.log.exception("Something awful happened trying to put that thing!")
        
        self.log.debug("Init done")
    

    @timed
    def handleAction(self, action, stream):
        #self.log.debug( "handle action")
        try :
            
            if action == "PONG" :
                login = stream.readQString()
                session = stream.readQString()
                self.ponged = True


            else :

                self.receiveJSON(action, stream)
            
        except :
            self.log.exception("Something awful happened in a gw thread !")

                
    @timed                
    def readDatas(self):
        try :
            self.log.debug("receiving data")
    
            if self.socket.bytesAvailable() == 0 :
                return       
            ins = QDataStream(self.socket)
            ins.setVersion(QDataStream.Qt_4_2)       
            while ins.atEnd() == False :
                if self.blockSize == 0:
                    if self.socket.bytesAvailable() < 4:
                        return
                    self.blockSize = ins.readUInt32()
                if self.socket.bytesAvailable() < self.blockSize:
                    return
                action = ins.readQString()
                self.log.info(action)
                self.handleAction(action, ins)
                self.blockSize = 0
        except :
            self.log.exception("Something awful happened in a gw thread !")
            
        
    @timed
    def disconnection(self):
        self.done()


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
      
    @timed
    def sendJSON(self, data_dictionary):
        '''
        Simply dumps a dictionary into a string and feeds it into the QTCPSocket
        '''

        data_string = ""
        try :
            data_string = json.dumps(data_dictionary)
        except :

            return

        
        self.sendReply(data_string)


    def jsonPlayer(self, player, session):
        #self.log.debug( "json player")
        jsonToSend = {}
        jsonToSend["command"] = "player_info"
        jsonToSend["login"] = str(player.getLogin())
        jsonToSend["uid"] = str(player.getId())
        jsonToSend["playersession"] = str(player.getSession())
        jsonToSend["session"] = session
        return jsonToSend


    def command_launch_game(self, message):
        self.log.debug("Launching a game !")
        try :
            planetuid   = message["planet"]
            defenders   = message["defenders"]
            attackers   = message["attackers"]
            
            faction_attackers =  message["faction_attackers"]
            faction_defenders =  message["faction_defenders"]
            luatable    = message["luatable"]
            
            attackers_fix = []
            defenders_fix = []
            
            for uid in defenders :
                if not int(uid) in defenders_fix :
                    defenders_fix.append(int(uid))

            for uid in attackers :
                if not int(uid) in attackers_fix :
                    attackers_fix.append(int(uid))
            
            self.parent.games.reloadContainer("gw")
            
            container = self.parent.games.getContainer("gw")
            if container != None :
                container.launchGame(self, planetuid, defenders_fix, attackers_fix, faction_defenders, faction_attackers, luatable)
   
        except :
            self.log.exception("Something awful happened in a gw thread !")
        
                

    def command_attack_check(self, message):
        self.log.debug("Checking an attack !")
        try: 
            planetuid   = message["planet"]
            defenders   = message["defenders"]
            attackers   = message["attackers"]
            
            resultDefend = {}
            resultAttack = {}
            
            for uid in defenders :
                resultDefend[uid] = False
                
            for uid in attackers :
                resultAttack[uid] = False
                    
            for uid in attackers :
                for user in self.parent.listUsers.getAllPlayers() :
                    if user.getId() == uid :
                        if user.getAction() == "NOTHING":
                            game = user.getGame()
                            if game :
                                realGame = self.parent.games.getGameByUuid(game)
                                if realGame :
                                    resultAttack[uid] = False
                                else :
                                    resultAttack[uid] = True
                            else :
                                resultAttack[uid] = True
                        else:
                            resultAttack[uid] = True                         
                        break
    
            for uid in defenders :
                for user in self.parent.listUsers.getAllPlayers() :                    
                    if user.getId() == uid :
                        if user.getAction() == "NOTHING":
                            game = user.getGame()
                            if game :
                                realGame = self.parent.games.getGameByUuid(game)
                                if realGame :
                                    resultDefend[uid] = False
                                else :
                                    resultDefend[uid] = True
                            else :
                                resultDefend[uid] = True 
                        else:
                            resultDefend[uid] = True
   
                        break
                    
            self.sendJSON(dict(command="attack", planet=planetuid, defenders = resultDefend, attackers = resultAttack))
        except :
            self.log.exception("Something awful happened in a gw thread !")
            
    def command_settings(self, message):
        port = message["port"]
        uid = message["uid"]

        for user in self.parent.listUsers.getAllPlayers() :
            if user.getId() == uid :
                user.setGamePort(port)
                return     
    
    
    
    def command_request(self, message):
        action = message["action"]

        if action == "player_info" :
            login = message["login"]
            for user in self.parent.listUsers.getAllPlayers() :
                if user.getLogin() == login :
                    
                    self.sendJSON(self.jsonPlayer(user, message["session"]))
                    
                    
    @timed    
    def receiveJSON(self, data_string, stream):
        '''
        A fairly pythonic way to process received strings as JSON messages.
        '''
        message = json.loads(data_string)

        cmd = "command_" + message['command']
        self.log.debug("receive JSON")
        self.log.debug(cmd)
        if hasattr(self, cmd):
            getattr(self, cmd)(message)  

    def preparePacket(self, action, *args, **kwargs) :

        reply = QByteArray()
        stream = QDataStream(reply, QIODevice.WriteOnly)
        stream.setVersion(QDataStream.Qt_4_2)
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

        return reply  
             
    def done(self) :
        
        
        if self in self.parent.recorders :
            #self.log.debug("removing pinger")

            #self.log.debug("removing socket")
            if self.socket != None :
                self.socket.readyRead.disconnect(self.readDatas)
                self.socket.disconnected.disconnect(self.disconnection)
                self.socket.error.disconnect(self.displayError)
                self.socket.abort()
                self.socket.deleteLater()
                #self.socket = None

                
            #self.log.debug("removing self")
            self.parent.removeRecorder(self)
        

    def sendReply(self, action, *args, **kwargs) :

        if self in self.parent.recorders :

    
            reply = QByteArray()
            stream = QDataStream(reply, QIODevice.WriteOnly)
            stream.setVersion(QDataStream.Qt_4_2)
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
            
            if self.socket.isValid() and self.socket.state() == 3 :
                
                if self.socket.write(reply) == -1 :
                    self.log.debug("error socket write")
                    self.socket.abort()
            else :
                self.log.debug("send reply - incorrect socket to write")
                self.socket.abort()

        
    @timed
    def stateChange(self, socketState):
        if socketState != QtNetwork.QAbstractSocket.ClosingState :
            self.log.debug("socket about to close")
        elif socketState != QtNetwork.QAbstractSocket.UnconnectedState :
            self.log.debug("socket not connected")
        
        if socketState != QtNetwork.QAbstractSocket.ConnectedState :
            self.log.debug("not connected")
            self.socket.abort()
    
    def displayError(self, socketError):
        if socketError == QtNetwork.QAbstractSocket.RemoteHostClosedError:
            self.log.warning( "RemoteHostClosedError")
     

        elif socketError == QtNetwork.QAbstractSocket.HostNotFoundError:
            self.log.warning("HostNotFoundError")
        elif socketError == QtNetwork.QAbstractSocket.ConnectionRefusedError:
            self.log.warning( "ConnectionRefusedError")
        else:
            self.log.warning("The following Error occurred: %s." % self.socket.errorString())

