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

import time

from PySide import QtSql
from server.decorators import with_logger

from server.games.game import Game, GameState


@with_logger
class GamesContainer(object):
    """Class for containing games"""
    listable = True

    def __init__(self, name, nice_name, db, games_service=None):
        self.games = []

        self.host = True
        self.live = True
        self.join = True
        
        self.type = 0

        self.desc = None

        self.gameTypeName = name
        self.gameNiceName = nice_name
        self.parent = games_service

        self.options = []

        self.db = db
        self._logger.debug("Initialized {}".format(nice_name))

        query = self.db.exec_("SELECT description FROM game_featuredMods WHERE gamemod = '%s'" % self.gameTypeName)
        if query.size() > 0:
            query.first()
            self.desc = query.value(0)  

    def getGamemodVersion(self):
        tableMod = "updates_" + self.gameTypeName
        tableModFiles = tableMod + "_files"
        value = {}
        query = QtSql.QSqlQuery(self.db)
        query.prepare("SELECT fileId, MAX(version) FROM `%s` LEFT JOIN %s ON `fileId` = %s.id GROUP BY fileId" % (tableModFiles, tableMod, tableMod))
        query.exec_()
        if query.size() != 0:
            while query.next():
                value[int(query.value(0))] = int(query.value(1)) 
        
        return value

    def createUuid(self, playerId):
        query = QtSql.QSqlQuery(self.db)
        queryStr = ("INSERT INTO game_stats (`host`) VALUE ( %i )" % playerId)
        query.exec_(queryStr)      
        uuid = query.lastInsertId()

        return uuid

    def findGameByUuid(self, uuid):
        """Find a game by the uuid"""
        for game in self.games:
            if game.uuid == uuid:
                return game
        return None

    def addGame(self, game):
        """Add a game to the list"""
        if not game in self.games:
            self.games.append(game)
            return 1
        return 0

    def addBasicGame(self, player, name):
        ngame = Game(self.createUuid(player.id), self)
        ngame.host = player
        ngame.name = name
        self.games.append(ngame)
        return ngame

