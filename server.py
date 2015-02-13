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

import sys

import logging
from logging import handlers
import signal
from quamash import QEventLoop
from PySide import QtSql, QtCore, QtNetwork
from PySide.QtSql import QSqlDatabase

from passwords import PRIVATE_KEY, DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_TABLE
from FaLobbyServer import FALobbyServer
from FaGamesServer import *
from src.players import *
import games

import config

logger = logging.getLogger(__name__)

UNIT16 = 8
if __name__ == '__main__':

    class Start(asyncio.Future):
        def __init__(self, loop):
            super(Start, self).__init__()
            self.rootlogger = logging.getLogger("")
            self.logHandler = handlers.RotatingFileHandler(config.LOG_PATH + "server.log", backupCount=1024, maxBytes=16777216 )
            self.logFormatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s')
            self.logHandler.setFormatter( self.logFormatter )
            self.rootlogger.addHandler( self.logHandler )
            self.rootlogger.setLevel(config.LOG_LEVEL)
            self.logger = logging.getLogger(__name__)

            self.players_online = playersOnline()

            self.db = QtSql.QSqlDatabase.addDatabase(QSqlDatabase("QMYSQL"))
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
            self.games = games.hyperGamesContainerClass(self.players_online, self.db, self.dirtyGameList)

            self.FALobby = FALobbyServer(self.players_online, self.games, self.db, self.dirtyGameList, self)
            self.FAGames = FAServer(loop, self.players_online, self.games, self.db, self.dirtyGameList, self)

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
            self.set_result(0)
            self.FALobby.close()
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

                for player in self.players_online.getAllPlayers() :
                    if player.getLogin() == playerName and player.getIp() == host.toString() :
                        player.setReceivedUdp(True)
                        player.setUdpPacketPort(port)
                        self.udpSocket.writeDatagram("packet Received", host, port)
                        break

    try:
        app = QtCore.QCoreApplication(sys.argv)
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)
        server = Start(loop)
        loop.run_until_complete(Start())

    except Exception as ex:
        logger.exception("Something awful happened!")
        logger.debug("Finishing main")
