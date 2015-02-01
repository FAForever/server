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


import sys, gc

import rsa, base64

from PySide.QtCore import QThread, QObject, SIGNAL, SLOT, QWriteLocker
from PySide.QtCore import QByteArray, QDataStream, QIODevice, QReadWriteLock
from PySide.QtNetwork import QTcpServer, QTcpSocket, QAbstractSocket, QHostInfo
  
from PySide import QtCore, QtNetwork, QtSql
from PySide.QtSql import *

import logging
from logging import handlers

from passwords import PRIVATE_KEY, DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_TABLE
from config import config

import uuid
import random

from FaLobbyServer import *
from FaGamesServer import *
from gwLobby import *
from players import *

import games

import signal 

from faPackets import Packet
UNIT16 = 8

class start(QObject):
    
    def __init__(self, parent=None):

        super(start, self).__init__(parent)
        self.rootlogger = logging.getLogger("")
        self.logHandler = handlers.RotatingFileHandler(config['global']['logpath'] + "server.log", backupCount=1024, maxBytes=16777216 )
        self.logFormatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s')
        self.logHandler.setFormatter( self.logFormatter )
        self.rootlogger.addHandler( self.logHandler )
        self.rootlogger.setLevel( eval ("logging." + config['server']['loglevel'] ))
        self.logger = logging.getLogger(__name__)
        
        # list of users
        self.listUsers = playersOnline()


        self.db= QtSql.QSqlDatabase.addDatabase("QMYSQL")
        self.db.setHostName(DB_SERVER)  
        self.db.setPort(DB_PORT)
        
        self.db.setDatabaseName(DB_TABLE)  
        self.db.setUserName(DB_LOGIN)  
        self.db.setPassword(DB_PASSWORD)
        
        self.privkey = PRIVATE_KEY

        self.db.setConnectOptions("MYSQL_OPT_RECONNECT=1")

        if not self.db.open():  
            self.logger.error(self.db.lastError().text())  
            sys.exit(1)  


        self.db.close()

        self.udpSocket = QtNetwork.QUdpSocket(self)
        self.udpSocket.bind(30351)
        self.udpSocket.readyRead.connect(self.processPendingDatagrams)
        self.dirtyGameList = []
        self.games = games.hyperGamesContainerClass(self.listUsers, self.db, self.dirtyGameList)
        
        self.FALobby = FALobbyServer(self.listUsers, self.games, self.db, self.dirtyGameList, self)
        self.GWLobby = GWLobbyServer(self.listUsers, self.games, self.db, self.dirtyGameList, self)
        self.FAGames = FAServer(self.listUsers, self.games, self.db, self.dirtyGameList, self)
        
        # Make sure we can shutdown gracefully
        signal.signal(signal.SIGTERM, self.signal_handler)
        

        if not self.GWLobby.listen(QtNetwork.QHostAddress.LocalHost, 8002):
            self.logger.error ("Unable to start the server")
            raise Exception("Unable to start the GW server" )
            return
        else:
            self.logger.info ("starting the GW server on  %s:%i" % (self.GWLobby.serverAddress().toString(),self.GWLobby.serverPort()))

        

        if not self.FAGames.listen(QtNetwork.QHostAddress.Any, 8000):
            self.logger.error ("Unable to start the server")
            raise Exception("Unable to start the game server")
            return
        else:
            self.logger.info ("starting the game server on  %s:%i" % (self.FAGames.serverAddress().toString(),self.FAGames.serverPort()))
        

        if not self.FALobby.listen(QtNetwork.QHostAddress.Any, 8001):
            self.logger.error ("Unable to start the lobby server")
            raise Exception("Unable to start the lobby server")
            return
        else:
            self.logger.info ("starting the Lobby server on  %s:%i" % (self.FALobby.serverAddress().toString(),self.FALobby.serverPort()))

    def signal_handler(self, signal, frame):
        self.logger.info("Received signal, shutting down")
        self.FALobby.close()
        self.GWLobby.close()
        self.FAGames.close()
        
    def jsonPlayer(self, player):
        ''' infos about a player'''
        jsonToSend = {}
        rating      = player.getRating()
        rating1v1   = player.getladder1v1Rating()
        jsonToSend["command"] = "player_info"
        jsonToSend["login"] = player.getLogin()        
        jsonToSend["rating_mean"] = rating.getRating().getMean()
        jsonToSend["rating_deviation"] = rating.getRating().getStandardDeviation()   
        # try:
        #     if player.view_globalMean and player.view_globalDev:
        #         jsonToSend["rating_mean"] = player.view_globalMean
        #         jsonToSend["rating_deviation"] = player.view_globalDev
        # except:
        #     pass
        # try:
        #     if player.view_globalMean and player.view_globalDev:
        #         jsonToSend["rating_mean"] = player.view_globalMean
        #         jsonToSend["rating_deviation"] = player.view_globalDev
        # except:
        #     pass     

        jsonToSend["ladder_rating_mean"] = rating1v1.getRating().getMean()
        jsonToSend["ladder_rating_deviation"] = rating1v1.getRating().getStandardDeviation()
        jsonToSend["number_of_games"] = player.getNumGames()
        jsonToSend["avatar"] = player.getAvatar()
        
        if hasattr(player, "leagueInfo") :
            jsonToSend["league"] = player.leagueInfo        
        
        if hasattr(player, "country") :
            if player.country != None :
                jsonToSend["country"] = player.country
        
        clan = player.getClan()
        if clan != None:
            jsonToSend["clan"] = player.getClan()
        else:
            jsonToSend["clan"] = ""
        
        return jsonToSend


    def processPendingDatagrams(self):
        ''' Handle UDP packets from the users. Used to check UDP connection on their side.'''
        while self.udpSocket.hasPendingDatagrams():
            datagram, host, port = self.udpSocket.readDatagram(self.udpSocket.pendingDatagramSize())

            splitter = str(datagram).split(" ")
            last = len(splitter)

            playerName = splitter[last-1]

            for player in self.listUsers.getAllPlayers() :
                if player.getLogin() == playerName and player.getIp() == host.toString() :
                    player.setReceivedUdp(True)
                    player.setUdpPacketPort(port)
                    self.udpSocket.writeDatagram("packet Received", host, port)
                    break

            
            


if __name__ == '__main__':
    
    try:
        logger = logging.getLogger(__name__)
        #gc.enable()
        #sys.setrecursionlimit(100)
        #gc.set_debug(gc.DEBUG_LEAK)
        app = QtCore.QCoreApplication(sys.argv)
        server = start()
        app.exec_()

    
    except Exception, ex:
        
        logger.exception("Something awful happened!")
        logger.debug("Finishing main")
