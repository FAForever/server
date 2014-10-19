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

import FaServerThread

import gc
import inspect

logger = logging.getLogger(__name__)

import teams

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


class FALobbyServer(QtNetwork.QTcpServer):
    def __init__(self, listUsers, Games, db, dirtyGameList, parent=None):
        super(FALobbyServer, self).__init__(parent)
        
        self.parent = parent
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Starting lobby server")
        self.logger.propagate = True

        
        self.teams = teams.Teams(self)

        self.dirtyGameList = dirtyGameList
        self.listUsers = listUsers
        self.games = Games

        self.db = db

        self.recorders = []
        self.socketToDelete = []

        # check every 5 seconds for new infos to send to the players about the game list.
        self.dirtyGameTimer = QtCore.QTimer(self)
        self.dirtyGameTimer.timeout.connect(self.dirtyGameCheck)
        self.dirtyGameTimer.start(5000)
        
        self.lastDirty = time.time()
        self.skippedDirty = 0
    
    def incomingConnection(self, socketId):
        reload(FaServerThread)
        self.recorders.append(FaServerThread.FAServerThread(socketId, self))    

    @timed
    def removeRecorder(self, recorder):
        if recorder in self.recorders:
            self.recorders.remove(recorder)
            recorder.deleteLater()

    @timed
    def addDirtyGame(self, game):
        if not game in self.dirtyGameList : 
            self.dirtyGameList.append(game)

    @timed
    def jsonGame(self, game):
        jsonToSend = {}
        jsonToSend["command"] = "game_info"
        jsonToSend["access"] = game.getAccess()
        jsonToSend["uid"] = game.getuuid()
        jsonToSend["title"] = game.getGameName()
        jsonToSend["state"] = game.getLobbyState()
        jsonToSend["featured_mod"]= game.getGamemod()
        jsonToSend["featured_mod_versions"] = game.getGamemodVersion()
        
        jsonToSend["sim_mods"]= game.getSimMods()
        jsonToSend["mapname"] = game.getMapName().lower()
        jsonToSend["host"] = game.getHostName()
        jsonToSend["num_players"] = game.getNumPlayer()
        jsonToSend["game_type"] = game.getGameType()
        jsonToSend["game_time"] = game.getTime()
        jsonToSend["options"] = game.getOptions()
        jsonToSend["max_players"] = game.getMaxPlayers()


        teams = game.getTeamsAssignements()

        teamsToSend = {}
        for k, v in teams.iteritems() :
            if len(v) != 0 :
                teamsToSend[k] = v


        jsonToSend["teams"] = teamsToSend

        # quality is computed lobby-side now. Was taking too much time server-side either way.
        #quality = game.getMatchQuality()
        #if quality != None :
        #   jsonToSend["quality"] = quality    
        
        return jsonToSend

    @timed
    def dirtyGameCheck(self):
        #self.logger.debug("dirtyGameCheck start")
        if time.time() - self.lastDirty > 5.2 and self.skippedDirty < 2 :
            self.logger.debug("skipping")
            #the server is probably laggin, we a beat
            self.lastDirty = time.time()
            self.skippedDirty = self.skippedDirty + 1 
        
        else :
            self.lastDirty = time.time()
            self.skippedDirty = 0
            reply = QtCore.QByteArray()
            
            for uid in self.dirtyGameList :
        
                game = self.parent.games.getGameByUuid(uid)
                if game != None :
                    container =  self.parent.games.getGameContainer(game)
                    if container.isListable() == True or container.isPrivateBeta() == False :
                        reply.append(self.prepareBigJSON(self.jsonGame(game)))
                else :
                    # the current uid doesn't have an associated game. It shouldn't happen, and the game is probably invalid.
                    # We send "empty" info to the players to be sure that the game is removed on his side.
                    jsonToSend = {}
                    jsonToSend["command"] = "game_info"
                    jsonToSend["uid"] = uid
                    jsonToSend["title"] = "unknown"
                    jsonToSend["state"] = "closed"
                    jsonToSend["featured_mod"]= "unknown"
                    jsonToSend["featured_mod_versions"] = {}
                    jsonToSend["sim_mods"]= []
                    jsonToSend["mapname"] = "unknown"
                    jsonToSend["host"] = "unknown"
                    jsonToSend["num_players"] = 0
                    jsonToSend["game_type"] = "unknown"
                    jsonToSend["game_time"] = 0
                    jsonToSend["max_players"] = 0
                    jsonToSend["teams"] = {}
                    jsonToSend["options"] = []
                    
                    reply.append(self.prepareBigJSON(jsonToSend))
                                       
                if uid in self.dirtyGameList : 
                    self.dirtyGameList.remove(uid)
            

            for lobby in self.recorders :
                    lobby.sendArray(reply)
                    


    @timed
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

    @timed
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
    def addSocketToDelete(self, socket):     
        self.socketToDelete.append([time.time(), socket])
            
    @timed
    def dump_garbage(self):

         f=open('debg.txt', 'w')
          #force collection
         f.write( "Collecting GARBAGE:")
         gc.collect()
          #prove they have been collected
         f.write("Collecting GARBAGE:")
         gc.collect()
         print len(gc.get_objects())
         print len(gc.garbage)

         f.write("\nGARBAGE OBJECTS:")

         f.close()

