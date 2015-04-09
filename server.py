#!/usr/bin/env python3

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
import asyncio

import sys
import logging
from logging import handlers
import signal

from quamash import QEventLoop
from PySide import QtSql, QtCore, QtNetwork
from PySide.QtCore import QTimer
from gameconnection import GameConnection

from passwords import PRIVATE_KEY, DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_TABLE
from server.FaLobbyServer import FALobbyServer
from server.games_service import GamesService
from server.players import *
import config


logger = logging.getLogger(__name__)

UNIT16 = 8
if __name__ == '__main__':
    class Start(QtCore.QObject, asyncio.Future):
        def __init__(self, loop):
            QtCore.QObject.__init__(self)
            asyncio.Future.__init__(self)

            import argparse
            parser = argparse.ArgumentParser(description='FAForever Server')
            parser.add_argument('--nodb', help="don't use a database",
                                          action='store_true')
            parser.add_argument('--db', help="use given database type",
                                        default='QMYSQL')
            args = parser.parse_args()


            self.rootlogger = logging.getLogger("")
            self.logHandler = handlers.RotatingFileHandler(config.LOG_PATH + "server.log", backupCount=1024, maxBytes=16777216)
            self.logFormatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s')
            self.logHandler.setFormatter(self.logFormatter)
            self.rootlogger.addHandler(self.logHandler)
            self.rootlogger.setLevel(config.LOG_LEVEL)
            self.logger = logging.getLogger(__name__)

            self.players_online = PlayersOnline()

            if args.nodb:
                from unittest import mock
                self.db = mock.Mock()
            else:
                self.db = QtSql.QSqlDatabase(args.db)
                self.db.setHostName(DB_SERVER)
                self.db.setPort(DB_PORT)

                self.db.setDatabaseName(DB_TABLE)
                self.db.setUserName(DB_LOGIN)
                self.db.setPassword(DB_PASSWORD)
                self.db.setConnectOptions("MYSQL_OPT_RECONNECT=1")

            self.privkey = PRIVATE_KEY

            if not self.db.open():
                self.logger.error(self.db.lastError().text())
                sys.exit(1)

            self.dirtyGameList = []
            self.games = GamesService(self.players_online, self.db)

            self.FALobby = FALobbyServer(self.players_online, self.games, self.db, self)
            self.game_server = loop.create_server(lambda:
                                                  GameConnection(loop,
                                                                 self.players_online,
                                                                 self.games,
                                                                 self.db,),
                                                  '', 8000)

            # Make sure we can shutdown gracefully
            signal.signal(signal.SIGTERM, self.signal_handler)
            signal.signal(signal.SIGINT, self.signal_handler)
            def poll_signal():
                pass
            timer = QTimer(self)
            timer.timeout.connect(poll_signal)
            timer.start(200)


            if not self.FALobby.listen(QtNetwork.QHostAddress.Any, 8001):
                self.logger.error("Unable to start the server {}".format(self.FALobby.serverError()))
                print("Unable to start the server {}".format(self.FALobby.serverError()))
                raise Exception("Unable to start the lobby server")
            else:
                self.logger.info("starting the Lobby server on  %s:%i" % (self.FALobby.serverAddress().toString(),self.FALobby.serverPort()))

        def signal_handler(self, signal, frame):
            self.logger.info("Received signal, shutting down")
            self.set_result(0)
            self.FALobby.close()
            self.game_server.close()
            self._loop.stop()

        def jsonPlayer(self, player):
            """ infos about a player"""
            return {"command": "player_info",
                    "login": player.getLogin(),
                    "rating_mean": player.global_rating[0],
                    "rating_deviation": player.global_rating[1],
                    "ladder_rating_mean": player.ladder_rating[0],
                    "ladder_rating_deviation": player.ladder_rating[1],
                    "number_of_games": player.numGames,
                    "avatar": player.avatar,
                    "league": getattr(player, 'leagueInfo', ''),
                    "country": getattr(player, 'country', ''),
                    "clan": getattr(player, 'clan', '')}

    try:
        app = QtCore.QCoreApplication(sys.argv)
        if config.LIBRARY_PATH:
            app.addLibraryPath('C:\\Qt\\4.8.6\\plugins')
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)
        loop.run_until_complete(Start(loop))

    except Exception as ex:
        logger.exception("Something awful happened {}".format(ex))
