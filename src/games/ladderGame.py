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
from src.abc.base_game import InitMode

logger = logging.getLogger(__name__)

from .game import Game

from PySide.QtSql import QSqlQuery
import operator


class ladder1V1Game(Game):
    """Class for 1v1 ladder game"""
    init_mode = InitMode.AUTO_LOBBY
    
    def __init__(self, uuid, parent = None):
        super(self.__class__, self).__init__(uuid, parent)

        self.hosted = False
        
        self.trueSkill1v1Players = []
        self.finalTeams1v1 = []
        self.invalidPlayers = []
        self.results = []
        self.playerToJoin = None
        self.minPlayer = 2
        self.leagues = {}

    def setLeaguePlayer(self, player):
        self.leagues[player.getLogin()] = player.league
         
    def checkNoScore(self):
        for player in self.players :
            if not player in self.gameResult:
                #if the player don't register, we set his score to 0
                self.gameResult[player] = 0

    def specialInit(self, player):          
        if player.getAction() == "HOST":
            self.playerToJoin.wantToConnectToGame = True
            
            map = self.mapName
            
            json = {
                "command": "game_launch",
                "mod": self.parent.gameTypeName,
                "reason": "ranked",
                "uid": self.uuid,
                "mapname": map,
                "args": ["/players 2", "/team 2"]
            }
            self.playerToJoin.lobbyThread.sendJSON(json)

            self.set_player_option(player.id, 'Team', 1)
            self.set_player_option(player.id, 'Army', 0)
            self.set_player_option(player.id, 'StartSpot', 0)
            self.set_player_option(player.id, 'Faction', player.faction)
            self.set_player_option(player.id, 'Color', 1)

        if player.getAction() == "JOIN":
            self.set_player_option(player.id, 'Team', 1)
            self.set_player_option(player.id, 'Army', 1)
            self.set_player_option(player.id, 'StartSpot', 1)
            self.set_player_option(player.id, 'Faction', player.faction)
            self.set_player_option(player.id, 'Color', 2)

            self.recombineTeams1v1()
            self.recombineTeams()

    def specialEnding(self, logger, db, players):
        if len(self.invalidPlayers) == 2:
            self.setInvalid("Scores not validated. Possible reason: Disconnection between players.")
        
        if self.valid:
            if self.isDraw():
                query = QSqlQuery(db)
                queryStr = ("SELECT id FROM table_map WHERE filename LIKE '%"+self.mapName+"%'")
                query.exec_(queryStr)

                if  query.size() == 1:
                    query.first()
                    mapId = query.value(0)
                
                    queryStr = ("UPDATE table_map_features set num_draws = (num_draws +1) WHERE map_id LIKE " + str(mapId))
                    query.exec_(queryStr)

            tsresults = self.computeResults1v1()
            tsplayers = self.getTrueSkill1v1Players()
            self.trueSkillUpdate(tsresults, tsplayers, logger, db, players, playerFnc="setladder1v1Rating" ,table="ladder1v1_rating", winner=True, sendScore=False)
        
            # and for the ladder !
            evenLeague = True
            maxleague = max(iter(self.leagues.items()), key=operator.itemgetter(1))[1]
            if len(set(self.leagues.values())) != 1 :
                evenLeague = False
                
            if not self.isDraw():
                query = QSqlQuery(db)
                for player in self.gameResult :
                    if self.isWinner(player) :
                        # if not even league:
                        scoreToAdd = 1
                        if not evenLeague:
                            if self.leagues[player] == maxleague:
                                scoreToAdd = 0.5
                            else :
                                scoreToAdd = 1.5
                            
                        query.prepare("UPDATE %s SET score = (score + ?) WHERE `idUser` = (SELECT id FROM login WHERE login.login = ?)" % self.parent.season)
                        query.addBindValue(scoreToAdd)
                        query.addBindValue(player)
                        query.exec_()
                        logger.debug(query.executedQuery())
                    else:
                        # if not even league:
                        scoreToRemove = 0.5
                        if not evenLeague :
                            if self.leagues[player] == maxleague:
                                scoreToRemove = 1
                            else :
                                scoreToRemove = 0

                        query.prepare("UPDATE %s SET score = GREATEST(0,(score - ?)) WHERE `idUser` = (SELECT id FROM login WHERE login.login = ?)" % self.parent.season)
                        query.addBindValue(scoreToRemove)
                        query.addBindValue(player)
                        query.exec_()
                        logger.debug(query.executedQuery()) 
                
                    #check if the user must be promoted
                    query.prepare("SELECT league, score FROM %s WHERE `idUser` = (SELECT id FROM login WHERE login.login = ?)" % self.parent.season)
                    query.addBindValue(player)
                    query.exec_()
                    if query.size() != 0:
                        query.first()
                        pleague = int(query.value(0))
                        pscore = float(query.value(1))
                        if pleague == 1 and pscore > 50:
                            query.prepare("UPDATE %s SET league = league+1, score = 0 WHERE `idUser` = (SELECT id FROM login WHERE login.login = ?)" % self.parent.season)
                            query.addBindValue(player)
                            query.exec_()
                        elif pleague == 2 and pscore > 75:                      
                            query.prepare("UPDATE %s SET league = league+1, score = 0 WHERE `idUser` = (SELECT id FROM login WHERE login.login = ?)" % self.parent.season)
                            query.addBindValue(player)
                            query.exec_()
                        elif pleague == 3 and pscore > 100:                      
                            query.prepare("UPDATE %s SET league = league+1, score = 0 WHERE `idUser` = (SELECT id FROM login WHERE login.login = ?)" % self.parent.season)
                            query.addBindValue(player)
                            query.exec_()
                        elif pleague == 4 and pscore > 150:                      
                            query.prepare("UPDATE %s SET league = league+1, score = 0 WHERE `idUser` = (SELECT id FROM login WHERE login.login = ?)" % self.parent.season)
                            query.addBindValue(player)
                            query.exec_()

                        for p in players.players() :
                            if str(p.getLogin()) == str(player) :
                                query.prepare("SELECT score, league FROM %s WHERE idUser = ?" % self.parent.season)
                                query.addBindValue(p.getId())
                                query.exec_()
                                if  query.size() > 0:
                                    query.first()
                                    score = float(query.value(0))
                                    league = int(query.value(1))
                                    
                                    query.prepare("SELECT name, `limit` FROM `ladder_division` WHERE `league` = ? AND `limit` >= ? ORDER BY `limit` ASC LIMIT 1")
                                    query.addBindValue(league)
                                    query.addBindValue(score)
                                    query.exec_()
                                    if query.size() > 0:
                                        query.first()
                                        p.setLeague(league)
                                        p.division = str(query.value(0))
        else :
            tsplayers = self.trueSkillPlayers
            for playerTS in tsplayers : 
                name = playerTS.getPlayer()
                self.sendMessageToPlayers(players, name, self.getInvalidReason())

    def addPlayerToJoin(self, player):
        self.playerToJoin = player

    def getPlayerToJoin(self):
        return self.playerToJoin
  
    def isDraw(self):
        if len(dict(list(zip(list(self.gameResult.values()),list(self.gameResult.keys()))))) == 1 :
            return True
        return False       
  
    def hostInGame(self):
        return self.hosted 

    def setHostInGame(self, state):
        self.hosted = state        

    def computeScoreFor1v1(self):
        results = []
        for teams in self.finalTeams1v1:
            curScore = 0
            for player in teams.players():
                if player.id in str(self.gameResult):
                    resultPlayer = self.gameResult[str(player.id)]
                    curScore = curScore + resultPlayer

            results.append(curScore)
            self.results = results

    def updateTrueskillFor1v1(self):
        """ Update all scores from the DB before updating the results"""
        try :
            for team in self.finalTeams1v1 :
                for member in team.players() :
                    query = QSqlQuery(self.parent.db)
                    query.prepare("SELECT mean, deviation FROM ladder1v1_rating WHERE id = (SELECT id FROM login WHERE login = ?)")
                    query.addBindValue(member.getId())
                    query.exec_()
                    self._logger.debug("updating a player")
                    if query.size() > 0:
                        query.first()
                        team.getRating(member).setMean(query.value(0))
                        team.getRating(member).setStandardDeviation(query.value(1))
                    else :
                        self._logger.debug("error updating a player")
                        self._logger.debug(member.getId())
        except :
            self._logger.exception("Something awful happened while updating trueskill!")

    # here we only take result, not score.
    def compute_rating(self, update=True):
        if update :
            self.updateTrueskill()
        
        
        self.computeScoreFor1v1()
        gameInfo = GameInfo()
        calculator = FactorGraphTrueSkillCalculator()
        try :
            newRatings = calculator.calculateNewRatings(gameInfo, self.finalTeams, self.results)
            return newRatings
        except :
            return 0
    
    def computeResults1v1(self):
        self.updateTrueskillFor1v1()
        self.computeScoreFor1v1()
        gameInfo = GameInfo()
        calculator = FactorGraphTrueSkillCalculator()
        
        try :
            newRatings = calculator.calculateNewRatings(gameInfo, self.finalTeams1v1, self.results)
            return newRatings
        except :
            return 0



    def recombineTeams1v1(self):
        teamsRecomb = []
        for team in self.teamAssign :
            if len(self.teamAssign[team]) != 0 and team != -1 :
                
                if team == 0 :
                    for player in self.teamAssign[team] :
                        curTeam = Team()
                        for playerTS in self.trueSkill1v1Players :

                            if str(playerTS.getPlayer()) == str(player) :

                                curTeam.addPlayer(playerTS.getPlayer(), playerTS.getRating())
                                
                                teamsRecomb.append(curTeam)
                else :
                    curTeam = Team()
                    for player in self.teamAssign[team] :
                        for playerTS in self.trueSkill1v1Players :
                            if str(playerTS.getPlayer()) == str(player) :
                                curTeam.addPlayer(playerTS.getPlayer(), playerTS.getRating())
                    teamsRecomb.append(curTeam)

        self.finalTeams1v1 = teamsRecomb

        return self.finalTeams1v1
        
    
