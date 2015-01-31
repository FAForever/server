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

from gamesContainer import  gamesContainerClass
from trueSkill.TrueSkill.FactorGraphTrueSkillCalculator import * 
from trueSkill.Team import *
from trueSkill.Teams import *


import random, sys
from ladder.ladderMaps import ladderMaps
from PySide import QtSql
from PySide import QtCore

from PySide.QtSql import *

import gameModes.gwgame
reload(gameModes.gwgame)
from gameModes.gwgame import gwGame

FACTIONS = {0:"UEF", 1:"Aeon",2:"Cybran",3:"Seraphim"}



class gwGamesContainerClass(gamesContainerClass):
    '''Class for 1vs1 ladder games'''
    
    def __init__(self, db, parent = None):
        super(gwGamesContainerClass, self).__init__("gw", "galactic war" ,db, parent)
        
        self.version = 93
        self.listable = False
        self.host = False
        self.join = False
        self.parent = parent

        self.lobby = None

    def createUuidGW(self, playerId, planetuid):
        query = QtSql.QSqlQuery(self.db)
        query.prepare("INSERT INTO galacticwar.game_stats (`host`, `planetuid`) VALUE (?,?)")
        query.addBindValue(playerId)
        query.addBindValue(planetuid)
        if not query.exec_():
            self.log.error(query.lastError()) 
        uuid = query.lastInsertId()
        return uuid

   
    def launchGame(self, parent, planetuid, defenders, attackers, faction_defenders, faction_attackers, luatable):
        #start game
        self.lobby = parent
     
        self.log.debug("launching a gw game !")
        try :
            self.log.debug("gw faction 1 " + str(faction_attackers))
            self.log.debug("gw faction 2 " + str(faction_defenders))
            if faction_attackers != None and faction_defenders != None:
                gameName = str(FACTIONS[faction_attackers] + " attacking " + FACTIONS[faction_defenders])
            else:
                gameName = str("untitled gw game")
            self.log.debug(gameName)
    
            players_attackers = []
            players_defenders = []
            
            for uid in attackers :
                for user in self.parent.players.getAllPlayers() :
                    if user.getId() == int(uid) :
                        players_attackers.append(user)
                        self.log.debug(user.getLogin())
                        
            for uid in defenders :
                for user in self.parent.players.getAllPlayers() :
                    if user.getId() == int(uid) :
                        players_defenders.append(user)
                        self.log.debug(user.getLogin())
            
            if len(players_attackers) != len(attackers) or len(players_defenders) != len(players_defenders):
                self.log.debug("Some players are missing")
                self.lobby.sendJSON(dict(command="game", state ="aborted", planetuid=planetuid))
                return
            
            if len(players_attackers) == 0 or len(players_defenders) == 0:
                self.log.debug("Some players are missing")
                self.lobby.sendJSON(dict(command="game", state ="aborted", planetuid=planetuid))
                return                
            
            numPlayers = len(players_attackers) + len(players_defenders)
            avataruid = players_attackers[0].getId()
            query = QSqlQuery(self.db)
            query.prepare("SELECT id FROM galacticwar.`avatars` WHERE `uid` = ? AND `alive` = 1")
            query.addBindValue(players_attackers[0].getId())
            query.exec_()
            if query.size() == 1 :
                query.first()
                avataruid = int(query.value(0))


            gameUuid = self.createUuidGW(avataruid, planetuid)

            players_attackers[0].setWantGame(True)
            
     
            for player in players_attackers :
                if player != players_attackers[0]: 
                    player.setAction("JOIN")
                else:
                    player.setAction("HOST")
                
            for player in players_defenders :
                player.setAction("JOIN")
                
            

            #self.db.open()
                
            query = QSqlQuery(self.db)
            query.prepare("SELECT filename FROM `table_map` WHERE `id` = (SELECT mapuid FROM galacticwar.planet_maps WHERE planetuid = ?)")
            query.addBindValue(planetuid)
            query.exec_()
            
            planetMap = "maps/canis3v3.v0001.zip"

            if query.size() > 0 :
                while query.next() :
                    planetMap = str(query.value(0))
    
               
            ngame = gwGame(gameUuid, self)
            
            
            ngame.setLogger("gwGame."+str(gameUuid))
            #self.db.close()
            
            planetMap = planetMap.split("/")[1][:-4]
            

            uuid = ngame.getuuid()
            
            self.lobby.sendJSON(dict(command="game_info", uuid=uuid, planetuid=planetuid))
            
            place = 1
            for player in players_attackers :
                player.setGame(uuid)
                ngame.assignPlayerToTeam(player.getLogin(), 1)
                ngame.placePlayer(player.getLogin(), place)
                place = place + 2
                

            place = 2
            for player in players_defenders :
                player.setGame(uuid)
                ngame.assignPlayerToTeam(player.getLogin(), 2)
                ngame.placePlayer(player.getLogin(), place)
                place = place + 2
                

            ngame.setLobbyState('Idle')
            ngame.log.debug("map is " + planetMap)
            ngame.setGameMap(planetMap)
            
            ngame.log.debug("getting avatar name for host " + players_attackers[0].getLogin())
            query = QSqlQuery(self.db)    
            query.prepare("SELECT name, id, faction FROM galacticwar.`avatars` LEFT JOIN galacticwar.`accounts` ON galacticwar.`avatars`.uid = galacticwar.`accounts`.uid WHERE galacticwar.`avatars`.`uid` = ? AND `alive` = 1")
            query.addBindValue(players_attackers[0].getId())
            query.exec_()
            if query.size() == 1 :
                query.first()
                name = str(query.value(0))
                uid = int(query.value(1))
                realfaction = int(query.value(2))
                ngame.setGameHostNameGW(name)
                ngame.avatarNames[players_attackers[0].getLogin()] = name
                ngame.avatarIds[players_attackers[0].getLogin()] = uid


            else :
                #no avatar found!?
                ngame.setLobbyState('closed')
                return
                ngame.setGameHostNameGW(players_attackers[0].getLogin())
                ngame.avatarNames[players_attackers[0].getLogin()] = players_attackers[0].getLogin()
                ngame.avatarIds[players_attackers[0].getLogin()] = players_attackers[0].getId()
                
            ngame.hostUuidGW = players_attackers[0].getId()
            ngame.setGameHostUuid(players_attackers[0].getId())

            ngame.setPlayerFaction(1, faction_attackers+1)
            ngame.setPlayerColor(1, 1)     

            ngame.setGameHostName(players_attackers[0].getLogin())
            
            ngame.setGameHostPort( players_attackers[0].getGamePort())
            ngame.setGameHostLocalPort( players_attackers[0].getGamePort())
            ngame.setGameName(gameName)
            ngame.setTime()
            
            ngame.planetuid = planetuid
            ngame.factionAttackers = faction_attackers
            ngame.factionDefenders = faction_defenders
            ngame.attackers = attackers
            ngame.defenders = defenders 
            ngame.numPlayers = numPlayers
            ngame.maxPlayer = numPlayers
            ngame.luatable = luatable
            #place the players
            for player in players_attackers :
                if player != players_attackers[0]:
                    ngame.addPlayerToJoin(player)
                
            for player in players_defenders :
                ngame.addPlayerToJoin(player)

            
            self.addGame(ngame)

            #get the real faction of the player.
            
            
            json = {}
            json["command"] = "game_launch"
            json["mod"] = self.gameTypeName
            json["mapname"] = str(planetMap)
            json["reason"] = "gw"
            json["uid"] = uuid
            json["luatable"] = luatable
            json["args"] = ["/players %i"%numPlayers, "/team 2", "/StartSpot 1", "/%s" % FACTIONS[realfaction]]
            
            
            players_attackers[0].getLobbyThread().sendJSON(json)
            
        except :
            self.log.exception("Something awful happened when launching a gw game !")

    def removeOldGames(self):
        '''Remove old games (invalids and not started)'''
        now = time.time()
        for game in reversed(self.games):

            diff = now - game.getTime()

            if game.getLobbyState() == 'open' and game.getNumPlayer() == 0 :
                
                game.setLobbyState('closed')      
                self.addDirtyGame(game.getuuid())        
                self.removeGame(game)

                continue

            if game.getLobbyState() == 'open' :
                host = game.getHostName()
                player = self.parent.players.findByName(host)

                if player == 0 : 
                    game.setLobbyState('closed')
                    self.addDirtyGame(game.getuuid())
                    self.removeGame(game)

                    continue
                else :
                    if player.getAction() != "HOST" :
                        
                        game.setLobbyState('closed')
                        self.addDirtyGame(game.getuuid())
                        self.removeGame(game)

                        continue

            
            if game.getLobbyState() == 'Idle' and diff > 60 :

                game.setLobbyState('closed')   
                self.addDirtyGame(game.getuuid())               
                self.removeGame(game)

                continue

            if game.getLobbyState() == 'playing' and diff > 60 * 60 * 8 : #if the game is playing for more than 8 hours

                game.setLobbyState('closed')
                self.addDirtyGame(game.getuuid())
                self.removeGame(game)

                continue
              