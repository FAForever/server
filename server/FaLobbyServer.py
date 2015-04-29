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

import logging

import json
import time

from PySide import QtCore, QtNetwork
import ujson

from server import lobbyconnection
from server.decorators import with_logger, timed
from server.games.game import GameState
from server.games_service import GamesService

from server.protocol.protocol import QDataStreamProtocol


logger = logging.getLogger(__name__)


@with_logger
class FALobbyServer(QtNetwork.QTcpServer):
    def __init__(self, listUsers, games: GamesService, db, parent=None):
        super(FALobbyServer, self).__init__(parent)
        
        self.parent = parent
        self._logger.debug("Starting lobby server")


        self.listUsers = listUsers
        self.games = games

        self.db = db

        self.recorders = []
        self.socketToDelete = []

        # check every 5 seconds for new infos to send to the players about the game list.
        self.dirtyGameTimer = QtCore.QTimer(self)
        self.dirtyGameTimer.timeout.connect(self.dirtyGameCheck)
        self.dirtyGameTimer.start(5000)
        
        self.lastDirty = time.time()
        self.skippedDirty = 0
    
    def incomingConnection(self, socket_id):
        """
        :param int socket_id: socket identifier
        :return:
        """
        socket = QtNetwork.QTcpSocket()
        if socket.setSocketDescriptor(socket_id):
            self.recorders.append(lobbyconnection.LobbyConnection(socket, self))
        else:
            self._logger.warning("Failed to handover socket descriptor for incoming connection")

    @timed()
    def removeRecorder(self, recorder):
        if recorder in self.recorders:
            self.recorders.remove(recorder)
            recorder.deleteLater()

    @timed()
    def addDirtyGame(self, game):
        if not game in self.dirtyGameList: 
            self.dirtyGameList.append(game)

    @timed
    def dirtyGameCheck(self):
        def encode(dictionary):
            return QDataStreamProtocol.pack_block(
                QDataStreamProtocol.pack_qstring(ujson.dumps(dictionary))
            )
        if time.time() - self.lastDirty > 5.2 and self.skippedDirty < 2:
            self._logger.debug("Not checking for dirty games")
            self.lastDirty = time.time()
            self.skippedDirty += 1
        
        else:
            self.lastDirty = time.time()
            self.skippedDirty = 0
            reply = QtCore.QByteArray()
            
            for uid in self.games.dirty_games:
        
                game = self.games.find_by_id(uid)
                if game is not None:
                    reply.append(encode(self.jsonGame(game)))
                else:
                    # If no game was found, send a bogus object to ensure client state updates
                    jsonToSend = {"command": "game_info",
                                  "uid": uid,
                                  "title": "unknown",
                                  "state": "closed",
                                  "featured_mod": "unknown",
                                  "featured_mod_versions": {},
                                  "sim_mods": [],
                                  "mapname": "unknown",
                                  "host": "unknown",
                                  "num_players": 0,
                                  "game_type": "unknown",
                                  "game_time": 0,
                                  "max_players": 0,
                                  "teams": {},
                                  "options": []}

                    reply.append(encode(jsonToSend))
                                       
                self.games.clear_dirty()

            for connection in self.recorders:
                if connection.loginDone:
                    connection.sendArray(reply)

