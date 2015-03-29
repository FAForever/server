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

    def rate_game(self):
        if self.valid:
            new_ratings = self.compute_rating()
            self.persist_rating_change_stats(new_ratings, rating='ladder1v1')

    def is_winner(self, player):
        return self.get_army_result(self.get_player_option(player.id, 'Army')) > 0

    def on_game_end(self):
        super().on_game_end()
        if not self.valid:
            return
        if self.isDraw():
            query = QSqlQuery(self.db)
            queryStr = ("SELECT id FROM table_map WHERE filename LIKE '%" + self.mapName + "%'")
            query.exec_(queryStr)
            while query.next():
                mapId = query.value(0)

                queryStr = ("UPDATE table_map_features set num_draws = (num_draws +1) WHERE map_id LIKE " + str(mapId))
                query = QSqlQuery(self.db)
                query.exec_(queryStr)
            return

        # And for the ladder !
        evenLeague = True
        maxleague = max(iter(self.leagues.items()), key=operator.itemgetter(1))[1]
        if len(set(self.leagues.values())) != 1:
            evenLeague = False

        query = QSqlQuery(self.db)
        for player in self.players:
            if self.is_winner(player):
                # if not even league:
                scoreToAdd = 1
                if not evenLeague:
                    if self.leagues[player] == maxleague:
                        scoreToAdd = 0.5
                    else :
                        scoreToAdd = 1.5

                query.prepare("UPDATE %s SET score = (score + ?) "
                              "WHERE `idUser` = ?" % self.parent.season)
                query.addBindValue(scoreToAdd)
                query.addBindValue(player.id)
                query.exec_()
                self._logger.debug(query.executedQuery())
            else:
                # if not even league:
                scoreToRemove = 0.5
                if not evenLeague:
                    if self.leagues[player] == maxleague:
                        scoreToRemove = 1
                    else :
                        scoreToRemove = 0

                query.prepare("UPDATE %s SET score = GREATEST(0,(score - ?))"
                              "WHERE `idUser` = ?" % self.parent.season)
                query.addBindValue(scoreToRemove)
                query.addBindValue(player.id)
                query.exec_()
                self._logger.debug(query.executedQuery())

            #check if the user must be promoted
            query.prepare("SELECT league, score FROM %s"
                          "WHERE `idUser` = ?" % self.parent.season)
            query.addBindValue(player.id)
            query.exec_()
            if query.size() != 0:
                query.first()
                pleague = int(query.value(0))
                pscore = float(query.value(1))
                # Minimum scores, by league, to move to next league
                league_incr_min = {1: 50, 2: 75, 3: 100, 4: 150}
                if pleague in league_incr_min and pscore > league_incr_min[pleague]:
                    query.prepare("UPDATE %s SET league = league+1, score = 0"
                                  "WHERE `idUser` = ?" % self.parent.season)
                    query.addBindValue(player.id)
                    query.exec_()

                for p in self.players:
                    query.prepare("SELECT score, league FROM %s WHERE idUser = ?" % self.parent.season)
                    query.addBindValue(p.id)
                    query.exec_()
                    if query.size() > 0:
                        query.first()
                        score = float(query.value(0))
                        league = int(query.value(1))

                        query.prepare("SELECT name, `limit` "
                                      "FROM `ladder_division` "
                                      "WHERE `league` = ? AND `limit` >= ?"
                                      "ORDER BY `limit` ASC LIMIT 1")
                        query.addBindValue(league)
                        query.addBindValue(score)
                        query.exec_()
                        if query.size() > 0:
                            query.first()
                            p.setLeague(league)
                            p.division = str(query.value(0))

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

    def get_army_result(self, army):
        """
        The head-to-head matchup ranking uses only win/loss as a factor
        :param army:
        :return:
        """
        for result in self._results[army]:
            if result[1] == 'victory':
                return 1
        return 0


