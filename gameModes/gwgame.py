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
logger = logging.getLogger(__name__)


import game
gameClass = reload(game)
from game import gameClass

import json
import time
from copy import deepcopy
from PySide.QtSql import QSqlQuery
import operator

from trueSkill.Team import *
from trueSkill.Teams import *
from trueSkill.Rating import *
from trueSkill.Player import *

from trueSkill.TrueSkill.FactorGraphTrueSkillCalculator import * 

import inspect


FACTIONS = {0:"UEF", 1:"Aeon",2:"Cybran",3:"Seraphim"}

RANKS = {0:["Private", "Corporal", "Sergeant", "Captain", "Major", "Colonel", "General", "Supreme Commander"],
         1:["Crusader", "Legate", "Avatar-of-War", "Priest", "Centurion", "Executor", "Evaluator", "Supreme Commander"],
         2:["Ensign", "Drone", "Agent", "Inspector", "Starshina", "Commandarm" ,"Elite Commander", "Supreme Commander"],
         3:["SouIstle", "Sou", "SouThuum", "YthiIstle", "Ythi", "YthiThuum", "Azeel", "Supreme Commander"]
         }

class gwGameClass(gameClass):
    '''Class for gw game'''
    
    def __init__(self, uuid, parent = None):
        super(self.__class__, self).__init__(uuid, parent)

       

        self.noStats = True
       
        self.hosted = False
        
        self.initMode = 1

        self.invalidPlayers = []
        self.results = []
        self.playerToJoin = [] 
        self.minPlayer = 2
        
        self.wrongReport = False
         

        
        self.recalled = []
        self.autorecalled = []
        self.startedAt = None
        self.curColor = 1

        self.numPlayers = 2
        
        self.gameStarted = False
        
        self.aborted = False
        self.reportedLeft = False

        self.avatarNames = {}
        self.avatarIds  = {}

        self.hostUuidGW = 0
        self.luatable = None
        
        self.deletedGroups = {}
        
    
    def setLogger(self, name):    
        self.log = logging.getLogger(__name__)
    
    def trueSkillUpdate(self, tsresults, tsplayers, logger, db, players, playerFnc = "setRating", table="global_rating", winner = False, sendScore = True):
        pass

    def addPlayerToJoin(self, player):
        if not player in self.playerToJoin : 
            self.playerToJoin.append(player)

    def getPlayerToJoin(self):
        return self.playerToJoin

    def checkNoScore(self):
        for player in self.getPlayers() :
            if not player in self.gameResult :
                #if the player don't register, we set his score to 0
                self.gameResult[player] = 0
                
    def deleteGroup(self, group, player):
        query = QSqlQuery(self.parent.db)    
        query.prepare("SELECT id FROM login WHERE `login` = ?")
        query.addBindValue(player)
        query.exec_()
        if query.size() == 1 :
            query.first()        
            uid = int(query.value(0))
            if not uid in self.deletedGroups:
                self.deletedGroups[uid] = []

            if not group in self.deletedGroups[uid]:
                self.parent.lobby.sendJSON(dict(command="delete_group", group=group, playeruid=uid))
                self.deletedGroups[uid].append(group)

    def isAllScoresThere(self):
        if len(self.gameFaResult) != self.numPlayers or len(self.gameResult) != self.numPlayers :
            return False
        
        foundAVictory = False
        for player in self.gameFaResult :
            if  self.gameFaResult[player] == "score" :
                return False
            if self.gameFaResult[player] == "victory" or self.gameFaResult[player] == "draw" :
                foundAVictory = True 
                self.log.debug("found a %s for player %s, ready to compute score." %( self.gameFaResult[player], player))
        return foundAVictory

    def getHostUidForJoin(self):
        return self.hostUuidGW

    def getSpecialUid(self, name):
        if name in self.avatarIds:
            return self.avatarIds[name]
        return name

    def getLoginName(self, name):
        for login in self.avatarNames:
            if self.avatarNames[login] == name:
                return login
        return name


    def placePlayer(self, player, position):
        #check if the player is already somewhere
        #get login name
        realName = self.getLoginName(player)
        
        
        key = self.returnKeyIndex(self.playerPosition, realName)
        #if so, delete his old place.
        if key != None :
            del self.playerPosition[key]
        
        if position != None :
            self.playerPosition[position] = str(realName)

        self.log.debug("place player " + realName + " in spot " + str(position))

    def setGameHostNameGW(self, name):
        self.gwHostName = name

    def getHostName(self):
        if inspect.stack()[1][3] == "jsonGame":
            return self.gwHostName
        return self.hostPlayer

    def getHostNameForJoin(self):
        return self.gwHostName

    def getPlayerRealFaction(self, uid):
            
        query = QSqlQuery(self.parent.db)    
        query.prepare("SELECT faction FROM galacticwar.`accounts` WHERE `uid` = ?")
        query.addBindValue(uid)
        query.exec_()
        if query.size() == 1 :
            query.first()
            return int(query.value(0))
        return None
        

    def getPlayerName(self, player):
        ''' Get the avatar name '''
        try :
            if player.getLogin() in self.avatarNames:
                return self.avatarNames[player.getLogin()]
            
            self.log.debug("getting avatar name for %s (uid %i)" % (player.getLogin(), player.getId()) )
            query = QSqlQuery(self.parent.db)
            
            uid = int(player.getId())
            
            query.prepare("SELECT name, id FROM galacticwar.`avatars` WHERE `uid` = ? AND `alive` = 1")
            query.addBindValue(uid)
            
            query.exec_()

            if query.size() == 1 :
                query.first()
                name = str(query.value(0))
                uid = int(query.value(1))
                self.avatarNames[player.getLogin()] = name
                self.avatarIds[player.getLogin()] = uid
                self.log.debug("avatar name is %s (uid %i)" % (name, uid) )
                return name
                
            else :
                self.avatarNames[player.getLogin()] = player.getLogin()
                self.avatarIds[player.getLogin()] = player.getId()

                return player.getLogin()
        except :
            self.log.exception("Something awful happened when getting a gw name !")
        

    def setLobbyState(self, state):
        self.log.debug("New lobby state : %s" % state)
        if state == '' :
            return 0
        else :
            self.lobbyState = state
        if not self.uuid:
            self.log.debug("No valid uuid")
         
        if state == "playing" :
            if not self.planetuid:
                self.log.debug("No valid planet uid")   
            self.gameStarted = True
            self.startedAt = time.time()
            self.log.debug("starting the game")
            self.parent.lobby.sendJSON(dict(command="game", state ="started", gameuid=self.uuid, planetuid=self.planetuid))
            
        if state == "closed" and self.gameStarted == False and self.aborted == False :
            if not self.planetuid:
                self.log.debug("No valid planet uid")   
            self.log.debug("aborting the game")
            self.aborted = True
            self.parent.lobby.sendJSON(dict(command="game", state ="aborted", gameuid=self.uuid, planetuid=self.planetuid))
            for curPlayer in self.players:
                if curPlayer.getLobbyThread() != None: 
                    curPlayer.getLobbyThread().sendJSON(dict(command="notice", style="kill"))            

    def removePlayer(self, player):
        """Remove a player from the game"""
        if player == '':
            return 0
        
        if self.gameStarted == False and self.reportedLeft == False :
            self.log.debug("Player %i has left the game" % player.getId())
            self.parent.lobby.sendJSON(dict(command="game", state ="left", gameuid=self.uuid, planetuid=self.planetuid, playeruid = player.getId()))
            self.reportedLeft = True
            
            for curPlayer in self.players:
                curPlayer.getLobbyThread().sendJSON(dict(command="notice", style="kill"))
            
        for curPlayer in self.players :
            if curPlayer.getLogin() == player.getLogin() :
                self.players.remove(curPlayer)
                self.removePlayerFromAllTeam(player.getLogin())
                return 1
        
        return 0        

    def addResultPlayer(self, player, faresult, score):

        if faresult == "recall" :
            self.log.debug("%s recalled" % player )
            if not player in self.recalled:
                self.recalled.append(player)
                self.gameResult[player] = -1
                self.gameFaResult[player] = faresult
                
        if faresult == "autorecall" :
            self.gameResult[player] = -1
            self.gameFaResult[player] = faresult
            self.log.debug("%s autorecalled" % player )
            if not player in self.autorecalled:
                self.autorecalled.append(player)
                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT id FROM login WHERE `login` = ?")
                query.addBindValue(player)
                query.exec_()
                if query.size() == 1 :
                    query.first() 
                    playerUid = int(query.value(0))
                    self.log.debug(playerUid)                
                    self.parent.lobby.sendJSON(dict(command="autorecall", playeruid=playerUid))
                

        if player in self.gameFaResult :
            self.log.debug("%s previous result : %s " % (player, self.gameFaResult[player]))
            self.log.debug("%s new result : %s " % (player, faresult))
            if  self.gameFaResult[player] == "score" :
                # the play got not decicive result yet, so we can apply it.
                self.gameFaResult[player] = faresult
                #self.gameResult[player] = score
            else :
                if faresult == "defeat":
                    if player in self.recalled or player in self.autorecalled:
                        self.log.debug("recalled to defeat -> invalid")
                        self.wrongReport = True
                    elif self.gameFaResult[player] == "victory"  :
                        if not player in self.invalidPlayers :
                            self.log.debug("victory to defeat !?")
                            #self.invalidPlayers.append(player)
                            
                    elif time.time() - self.startedAt < ((60*4) + 10) :
                        self.log.debug("too soon to die...")
                        self.setInvalid("Game is invalid : Play time was not long enough.")
                        
                    #if we try to set a defeat, but the player was victory.. We've got a disparity problem !
                    #
                else :
                    if faresult != "score" :
                        self.gameFaResult[player] = faresult
                        if faresult == "defeat" :
                            self.gameResult[player] = -1
                        elif faresult == "recall" or faresult == "autorecall":
                            self.gameResult[player] = -1
                        elif faresult == "victory" :
                            self.gameResult[player] = 1
                        elif faresult == "draw" :       
                            self.gameResult[player] = -1                 
        else :
            self.log.debug("%s result : %s " % (player, faresult))
            if faresult != "score" :
                self.gameFaResult[player] = faresult
                if faresult == "defeat" :
                    self.gameResult[player] = -1
                elif faresult == "recall" or faresult == "autorecall":
                    self.gameResult[player] = -1
                elif faresult == "victory" :
                    self.gameResult[player] = 1
                elif faresult == "draw" :       
                    self.gameResult[player] = -1   

    def specialInit(self, player):          
        try :
            self.log.debug("init gw")
            self.log.debug("player " + str(player.getLogin()))
            #print "custom special init"
            trueskill = player.getRating()
            trueSkillCopy = deepcopy(trueskill)
            self.addTrueSkillPlayer(trueSkillCopy)
            
            if player.getAction() == "HOST" :
                
                playerToJoin = self.getPlayerToJoin()
                map = str(self.getMapName())
                
                for p in playerToJoin :
                    place = self.getPositionOfPlayer(p.getLogin())  
                    if p.getId() in self.attackers :
                        faction = self.factionAttackers
                        team = 2
                        
                    else :
                        faction = self.factionDefenders
                        team = 3
                        
                    self.setPlayerFaction(place, faction+1)
                    self.setPlayerColor(place, place)
                    
                    p.setWantGame(True)

                    json = {}
                    json["command"] = "game_launch"
                    json["mod"] = self.parent.gameTypeName
                    json["reason"] = "gw"
                    json["uid"] = self.uuid
                    json["mapname"] = map
                    json["luatable"] = self.luatable
    
                    self.log.debug("Host is %s" % player.getLogin() )
                    self.log.debug("launching FA for %s, place %i" % (p.getLogin(),place) )
                    
    
                    realFaction = self.getPlayerRealFaction(p.getId())
                    if realFaction == None:
                        realFaction = faction
                    
                    json["args"] = ["/players %i" % self.numPlayers, "/team %i" % team, "/StartSpot %i" % place, "/%s" % FACTIONS[realFaction]]
                    p.getLobbyThread().sendJSON(json)
                    
                
                self.parent.lobby.sendJSON(dict(command="game", state ="hosted", gameuid=self.uuid, planetuid=self.planetuid))
            
            self.parent.lobby.sendJSON(dict(command="game", state ="player_join", gameuid=self.uuid, planetuid=self.planetuid, playeruid=player.getId()))
            
        except :
            self.log.exception("Something awful happened when launching a gw game !")

    def getTeamsAssignements(self):
        ''' for GW, we are returning the avatar name, not the real one !'''
        altertedTeams = {}
        for team in self.teamAssign:
            altertedTeams[team] = []
            for player in self.teamAssign[team]:
                avatarName = player
                if player in self.avatarNames:
                    avatarName = self.avatarNames[player]
                altertedTeams[team].append(avatarName)

        return altertedTeams

    def specialEnding(self, logger, db, players):
        try :
            self.log.debug("special ending.")

            if len(self.invalidPlayers) == self.numPlayers or self.wrongReport == True:
                
                if self.wrongReport:
                    self.log.debug("Recalled player declared defeated.. Player recalled:")
                    for p in self.recalled:
                        self.log.debug(p)
                    self.log.debug("Scores")
                    self.log.debug(self.gameResult)
                        
                    self.log.debug("Recalled player declared defeated..")
                else:
                    self.log.debug("Invalid : self.invalidPlayers == numPlayer")
                self.parent.lobby.sendJSON(dict(command="results", gameuid=self.uuid, planetuid=self.planetuid, results={}))            
                return False
            
            #computing winning team
            teams = self.finalTeams
    
            teamsResults = {}
            
            teamsResults[1] = {}
            teamsResults[2] = {}
            
            teamsResults[1]["players"] = {}
            teamsResults[2]["players"] = {}
            
            for teams in self.finalTeams :
                
                curScore = 0
                for player in teams.getAllPlayers() :
                    uid = player.getId()
                    self.log.debug("searching")
                    self.log.debug(uid)
                    
                    query = QSqlQuery(self.parent.db)
                    query.prepare("SELECT id FROM login WHERE `login` = ?")
                    query.addBindValue(uid)
                    query.exec_()

                    playerUid = 1
                    
                    if query.size() == 1 :
                        query.first() 
                        self.log.debug("found uid")
                        playerUid = int(query.value(0))
                        self.log.debug(playerUid)
                                           
                    
                    if playerUid in self.attackers :
                        i = 1
                    else :
                        i = 2
                        
                    
    
                    if uid in str(self.gameResult) :
                        
                        resultPlayer = self.gameResult[uid]
                        
                        if resultPlayer <= -1 :
                            if  uid in self.recalled  :
                                teamsResults[i]["players"][playerUid] = 0
                            elif uid in self.autorecalled:
                                teamsResults[i]["players"][playerUid] = -1
                            else :
                               teamsResults[i]["players"][playerUid] = -2
                        else :
                            teamsResults[i]["players"][playerUid] = 1
                        
                        curScore =  curScore + resultPlayer
                        
                    else :
                        
                        self.parent.lobby.sendJSON(dict(command="results", gameuid=self.uuid, planetuid=self.planetuid, results={}))
                        self.log.debug("score not found for %s" % str(uid))
                        return 0
    
                teamsResults[i]["score"] = curScore
    
            if self.desync < 2:
                results = json.dumps(teamsResults)
                self.log.debug(teamsResults)
            
                self.parent.lobby.sendJSON(dict(command="results", gameuid=self.uuid, planetuid=self.planetuid, results=results))
            else:
                self.log.debug(self.getInvalidReason())
                self.parent.lobby.sendJSON(dict(command="results", gameuid=self.uuid, planetuid=self.planetuid, results={}))
        except :
            self.log.exception("Something awful happened when finishing a gw game !")

