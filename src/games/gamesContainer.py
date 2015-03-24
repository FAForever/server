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
import logging

from PySide import QtSql

from src.games.game import Game, GameState


class GamesContainer(object):
    """Class for containing games"""
    listable = True

    def __init__(self, gameTypeName, gameNiceName, db, parent = None):

        self.log = logging.getLogger(__name__)

        self.log.debug("initializing " + self.__class__.__name__)
        
        self.games = []

        self.host = True
        self.live = True
        self.join = True
        
        self.type = 0

        self.desc = None

        self.gameTypeName = gameTypeName
        self.gameNiceName = gameNiceName
        self.parent = parent

        self.options = []

        self.db = db
        
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
        if query.size() != 0 :
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
            if game.uuid == uuid :
                return game
        return None

    def addGame(self, game):
        """Add a game to the list"""
        if not game in self.games :
            self.games.append(game)
            return 1
        return 0

    def addBasicGame(self, player, name, gamePort):
        playerLogin = player.getLogin()
        playerUuid = player.getId()
        playerState = player.action
        gameUuid = self.createUuid(playerUuid)

        if playerState == "PLAYING":
            return False
        elif playerState == "HOST":
            return False
        elif playerState == "JOIN":
            return False

        ngame = Game(gameUuid, self)
        ngame.setGameHostName(playerLogin)
        ngame.setGameHostUuid(playerUuid)
        ngame.setGameHostPort(gamePort)
        ngame.setGameHostLocalPort(gamePort)
        ngame.setGameName(name)
        self.games.append(ngame)
        return ngame

    def removeGame(self, gameToRemove):
        """Remove a game from the list"""

        for game in reversed(self.games):
            if game == gameToRemove :
                game.state = GameState.ENDED
                self.addDirtyGame(game.uuid)
                self.games.remove(game)

                return True

    def addDirtyGame(self, game):
        if not game in self.parent.dirtyGameList : 
            self.parent.dirtyGameList.append(game)           
            
    def removeOldGames(self):
        """Remove old games (invalids and not started)"""

        now = time.time()

        ''' Returns true if a game should be kept alive, false if it should die '''
        def validateGame(game):
            diff = now - game.created_at
            if game.lobbyState == 'open':
                if len(game.players) == 0:
                    return False

                hostPlayer = self.parent.players.findByName(game.hostPlayer)

                if hostPlayer == 0:
                    return False
                else:
                    if hostPlayer.getAction() != "HOST":
                        return False

            if game.lobbyState == 'Idle' and diff > 60:
                return False

            if game.lobbyState == 'playing' and diff > 60 * 60 * 8 : #if the game is playing for more than 8 hours
                return False

        for game in reversed(self.games):

            if not validateGame(game):
                game.state = GameState.ENDED
                self.addDirtyGame(game.uuid)
                self.removeGame(game)
