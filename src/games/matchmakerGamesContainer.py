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


import math
import random

from PySide.QtSql import *

from src.games.gamesContainer import  gamesContainerClass
from .matchmakerGame import matchmakerGame


FACTIONS = {1:"UEF", 2:"Aeon",3:"Cybran",4:"Seraphim"}

class team(object):
    """ class for a team of players """

    def __init__(self, number):
        self.number = number
        self.players = []

        self.uid = random.getrandbits(32)

        self.teamAverage = self.computeAveragePlayer()

    def getNumber(self):
        return self.number

    def setNumber(self, numPlayersWanted):
        
        self.number = max(numPlayersWanted, len(self.players))

    def getTrueskillTeam(self):
        curTeam = Team()
        for player in self.players:
            tsPlayer = player.getRating()
            curTeam.addPlayer(tsPlayer.getPlayer(), tsPlayer.getRating())
        return curTeam

    def emptyTeam(self):
        self.players = []
        self.number = 0

    def addPlayers(self, players = []):
        """ add players to the team"""
        for player in players:
            if not player in self.players and len(self.players) < self.number:
                self.players.append(player)

        self.teamAverage = self.computeAveragePlayer()

    def removePlayers(self, players = []):
        """ remove players from the team"""
        for player in players:
            if player in self.players:
                self.players.remove(player)

        self.teamAverage = self.computeAveragePlayer()

    def removePlayer(self, player):
        """ remove player from the team"""
        if player in self.players:
            self.players.remove(player)

        self.teamAverage = self.computeAveragePlayer()

    def getNumPlayers(self):
        return len(self.players)

    def isComplete(self):
        if len(self.players) == self.number:
            return True
        return False

    def getUid(self):
        return self.uid

    def playersMissing(self):
        return self.number - len(self.players)

    def isMissingPlayer(self):
        if (self.number - len(self.players)) != 0:
            return True
        return False

    def getPlayers(self):
        return self.players

    def getAveragePlayer(self):
        return self.teamAverage

    def computeAveragePlayer(self):
        """ compute a average of all players skill """

        if self.getNumPlayers() > 0:
            allMeans = []
            allVariances = []
            for player in self.players:
                tsPlayer = player.getRating()
                allMeans.append(tsPlayer.getRating().getMean())
                allVariances.append(tsPlayer.getRating().getStandardDeviation() * tsPlayer.getRating().getStandardDeviation())

            avgMean = sum(allMeans) / len(allMeans)
            avgDev = math.sqrt(sum(allVariances) / (len(allVariances)*len(allVariances)))

            return faPlayer(Player("averageTeam"), Rating(avgMean,avgDev))

        return faPlayer(Player("averageTeam"), Rating(1500,500))

class teamsManager(object):
    """ class for managing teams """
    def __init__(self, parent = None):
        self.teams = {}
        self.parent = parent



    def deleteTeam(self, uid):
        if uid in self.teams:
            del self.teams[uid]


    def createTeam(self, number, players = []):
        newTeam = team(number)
        uid = newTeam.getUid()
        newTeam.addPlayers(players)

        self.teams[uid] = newTeam

        if newTeam.isComplete():
            self.searchForMatchup(uid)
        else:
            self.searchForTeam(uid)

    # def addPlayersToTeam(self, teamuid, numPlayersWanted, players = []):

    #     if teamuid in self.teams:
    #         self.teams[teamuid].addPlayers(players)

    #         if numPlayersWanted != self.teams[teamuid].getNumber():
    #             self.teams[teamuid].setNumber(numPlayersWanted)
    #     else:
    #         #TODO :
    #         # handle lobby if the team is no longer existing.
    #         pass

    #     if self.teams[teamuid].isComplete():
    #         self.searchForMatchup(teamuid)   

    def getMatchQuality(self, team1, team2):
        
        matchup = [team1.getTrueskillTeam(), team2.getTrueskillTeam()]        
        gameInfo = GameInfo()
        calculator = FactorGraphTrueSkillCalculator()
        return calculator.calculateMatchQuality(gameInfo, matchup)

    def getMatchQuality2Players(self, player1, player2):
        
        matchup = [player1, player2]
        
        gameInfo = GameInfo()
        calculator = FactorGraphTrueSkillCalculator()
        return calculator.calculateMatchQuality(gameInfo, matchup)


    def mergeTeams(self, uidteam1, uidteam2):
        """ merge two teams """
        self.parent.log.debug("previous size of team1 " + str(self.teams[uidteam1].getNumPlayers()) )
        self.parent.log.debug("previous size of team2 " + str(self.teams[uidteam2].getNumPlayers()) )
        self.parent.log.debug("merging " + str(uidteam1) + " with " + str(uidteam2))
        self.teams[uidteam1].addPlayers(self.teams[uidteam2].players)

        p1names = []
        p2names = []

        for player in self.teams[uidteam1].players:
            p1names.append(player.getLogin())
        for player in self.teams[uidteam2].players:
            p2names.append(player.getLogin())

        gameName = str( ",".join(p1names) + " Merged with " + ",".join(p2names))        
        self.parent.log.debug(gameName)

        self.teams[uidteam2].emptyTeam()
        # and we disband team2
        self.parent.log.debug("size of team1 " + str(self.teams[uidteam1].getNumPlayers()) )
        self.parent.log.debug("size of team2 " + str(self.teams[uidteam2].getNumPlayers()) )
        #del self.teams[uidteam2]

    def getMinimumQuality(self, deviation):
        gameQuality = 0.8
        if deviation > 450 :
            gameQuality = 0.01               
        elif deviation > 350 :
            gameQuality = 0.1
        elif deviation > 300 :
            gameQuality = 0.7               
        elif deviation > 250 :
            gameQuality = 0.75
        else :
            gameQuality = 0.8

        return gameQuality

    def cleanTeams(self):
        toDelete = []
        for uid in self.teams:
            team = self.teams[uid]

            if team.getNumPlayers() == 0:
                toDelete.append(uid) 
        
        for uid in toDelete:
            del self.teams[uid]

    def searchForTeam(self, teamuid):
        """ adding players to existing teams """
        self.cleanTeams()

        if not teamuid in self.teams:
            return
        
        searchTeam = self.teams[teamuid]
        playersWanted = searchTeam.playersMissing()
        teamAvg = searchTeam.getAveragePlayer()
        deviation = teamAvg.getRating().getStandardDeviation()

        #minimum game quality to add the player
        gameQuality = self.getMinimumQuality(deviation)
        self.parent.log.debug("Searching team for " + str(teamuid) + " with gamequality at least " + str(gameQuality) + " (deviation of " + str(deviation) + ")")

        for uid in self.teams:
            curTeam = self.teams[uid]

            if curTeam.getNumPlayers() == 0:
                continue

            if uid == teamuid or curTeam == searchTeam:
                continue

            if curTeam.getNumber() != searchTeam.getNumber():
                continue

            if curTeam.getNumPlayers() > playersWanted:
                continue

            teamOk = True
            # now we test all the player
            for player in curTeam.players:

                curMatchQuality = self.getMatchQuality2Players(player.getRating(), teamAvg)
                if curMatchQuality < gameQuality :
                    # if one player doesn't fit, we dismiss the team
                    teamOk = False
                    break
            #if all members were okay, we can merge the teams
            if teamOk:
                self.mergeTeams(teamuid, uid)
                self.parent.log.debug("checking if " + str(teamuid) + " is complete")
                # if the team is complete now, we search for matchup
                if self.teams[teamuid].isComplete():
                    self.parent.log.debug("it is complete!")
                    self.searchForMatchup(teamuid)
                    break

    def searchForMatchup(self, teamuid):

        """ match a team against another """
        self.cleanTeams()
        if not teamuid in self.teams:
            return
        searchTeam = self.teams[teamuid]
        deviation = searchTeam.getAveragePlayer().getRating().getStandardDeviation()
        #minimum game quality to add the player
        gameQuality = self.getMinimumQuality(deviation)

        maxQuality = 0
        bestMatchup = None
        bestMatchupUid = None
        for uid in self.teams:
            curTeam = self.teams[uid]

            if uid == teamuid or curTeam == searchTeam:
                continue

            if not curTeam.isComplete():
                continue

            if curTeam.getNumber() != searchTeam.getNumber():
                continue

            # now we test the balance of the game
            curMatchQuality = self.getMatchQuality(searchTeam, curTeam)
            if curMatchQuality < gameQuality :
                continue

            if curMatchQuality > maxQuality :
                maxQuality = curMatchQuality
                bestMatchup = curTeam     
                bestMatchupUid = uid       

        if bestMatchup:
            self.parent.startGame(searchTeam.players, bestMatchup.players, teamuid, bestMatchupUid)
            pass

class matchmakerGamesContainerClass(gamesContainerClass):
    """Class for matchmaker games"""
    
    def __init__(self, db, parent = None):
        super(matchmakerGamesContainerClass, self).__init__("matchmaker", "Matchmaker" ,db, parent)

        self.manager = teamsManager(self)
        self.listable = False
        self.host = False
        self.join = False
        self.parent = parent


    def addPlayers(self, numPlayersWanted, players = []):
        # first remove players from existing teams
        self.removePlayers(players)

        for p in players:
            p.setAction("SEARCH_LADDER")

        self.manager.createTeam(numPlayersWanted, players)


    def startGame(self, players1, players2, teamuid, bestMatchupUid) :
        #start game
        
        if len(players1) != len(players2):
            return

        if len(players1) == 0:
            return

        # check that no one is playing....
        canStart = True
        for player in players1:
            if player.getAction() != "SEARCH_LADDER":
                self.removePlayer(player)
                canStart = False
                player.lobbyThread.command_quit_team(dict(command="quit_team"))

        for player in players2:
            if player.getAction() != "SEARCH_LADDER":
                self.removePlayer(player)
                canStart = False
                player.lobbyThread.command_quit_team(dict(command="quit_team"))


        if not canStart:
            for p in players1+players2:
                p.lobbyThread.sendJSON(dict(command="matchmaker_info", action="stopSearching"))
            return

        #first clean old games that didnt start.
        for game in self.games :
            if game.lobbyState == 'Idle' :
                for player in game.players :
                    for p in players1 + players2:
                        if player.getLogin() == p.getLogin() or player.getLogin() == p.getLogin() :
                            self.remove(game)
                            continue

        p1names = []
        p2names = []
        p1uids = []
        p2uids = []
        for player in players1:
            p1names.append(player.login)
            p1uids.append(str(player.id))
        for player in players2:
            p2names.append(player.login)
            p2uids.append(str(player.id))

        gameName = str( ",".join(p1names) + " Vs " + ",".join(p2names))
        
        #creating the game
        for p in players1+players2:
            p.setAction("JOIN")


        host = players1[0]
        host.setAction("HOST")
        
        gameUuid = self.createUuid(host.id)
        
        self.log.debug(str(gameUuid) + " " + gameName)
        host.wantToConnectToGame = True

        mapname = "scmp_007"
        #self.db.open()
            
        query = QSqlQuery(self.db)
        # get player map selection for players 1
        mapsP1 = []
        query.prepare("SELECT idMap FROM ladder_map_selection LEFT JOIN table_map ON `idMap` = table_map.id WHERE idUser in (%s) AND table_map.max_players >= ?" % ",".join(p1uids))
        query.addBindValue(len(players1)*2)
        query.exec_()
        if query.size() > 0:
            while next(query):
                mapsP1.append(int(query.value(0)))

        # get player map selection for player 2
        mapsP2 = []
        query.prepare("SELECT idMap FROM ladder_map_selection LEFT JOIN table_map ON `idMap` = table_map.id WHERE idUser in (%s) AND table_map.max_players >= ?" % ",".join(p2uids))
        query.addBindValue(len(players1)*2)
        query.exec_()
        if query.size() > 0:
            while next(query):
                mapsP2.append(int(query.value(0)))
                
        commonMaps = list(set(mapsP1).intersection(set(mapsP2)))
        
        if len(commonMaps) < 15 :
            
            moreMaps = 15 - len(commonMaps)
            choice = random.randint(0,2)

            if len(mapsP1) == 0 and choice == 1:
                choice = 0

            if len(mapsP2) == 0 and choice == 2:
                choice = 0

            if choice == 0:
                # not enough common maps, we fill with more maps.
                query.prepare("SELECT `idMap` FROM `ladder_map_selection` LEFT JOIN table_map ON `idMap` = table_map.id WHERE table_map.max_players >= ? GROUP BY `idMap` ORDER BY count( `idUser` ) DESC LIMIT %i" % moreMaps)
                query.addBindValue(len(players1)*2)
                query.exec_()
                if query.size() > moreMaps:
                    while next(query):
                        commonMaps.append(int(query.value(0)))
                else:


                    query.prepare("SELECT `idMap` FROM `ladder_map` LEFT JOIN table_map ON `idMap` = table_map.id WHERE table_map.max_players >= ? ORDER BY RAND() DESC LIMIT %i" % moreMaps)
                    query.addBindValue(len(players1)*2)
                    query.exec_()
                    if query.size() > 0:
                        while next(query):
                            commonMaps.append(int(query.value(0)))
            
            elif choice == 1:
                random.shuffle(mapsP1)
                if len(mapsP1) >= moreMaps:
                    commonMaps = commonMaps + mapsP1[:moreMaps]
                else:
                    commonMaps = commonMaps + mapsP1
                    remainingMaps = 15 - len(commonMaps)
                    query.prepare("SELECT `idMap` FROM `ladder_map_selection` LEFT JOIN table_map ON `idMap` = table_map.id WHERE table_map.max_players >= ? GROUP BY `idMap` ORDER BY count(`idUser`) DESC LIMIT %i" % remainingMaps)
                    query.addBindValue(len(players1)*2)
                    query.exec_()
                    if query.size() > remainingMaps:
                        while next(query):
                            commonMaps.append(int(query.value(0)))                    
                    else:
                        query.prepare("SELECT `idmap` FROM `ladder_map` LEFT JOIN table_map ON `idMap` = table_map.id WHERE table_map.max_players >= ? ORDER BY RAND( ) LIMIT %i" % remainingMaps)
                        query.addBindValue(len(players1)*2)
                        query.exec_()
                        if query.size() > 0:
                            while next(query):
                                commonMaps.append(int(query.value(0)))                    
                     
            elif choice == 2:
                random.shuffle(mapsP2)
                if len(mapsP2) >= moreMaps:
                    commonMaps = commonMaps + mapsP2[:moreMaps]
                else:
                    commonMaps = commonMaps + mapsP2
                    remainingMaps = 15 - len(commonMaps)
                    query.prepare("SELECT `idMap` FROM `ladder_map_selection` LEFT JOIN table_map ON `idMap` = table_map.id WHERE table_map.max_players >= ? GROUP BY `idMap` ORDER BY count(`idUser`) DESC LIMIT %i" % remainingMaps)
                    query.addBindValue(len(players1)*2)
                    query.exec_()
                    if query.size() > remainingMaps:
                        while next(query):
                            commonMaps.append(int(query.value(0)))                    
                    else:
                        query.prepare("SELECT `idmap` FROM `ladder_map` LEFT JOIN table_map ON `idMap` = table_map.id WHERE table_map.max_players >= ? ORDER BY RAND( ) LIMIT %i" % remainingMaps)
                        query.addBindValue(len(players1)*2)
                        query.exec_()
                        if query.size() > 0:
                            while next(query):
                                commonMaps.append(int(query.value(0)))                                        
        
        mapChosen = random.choice(commonMaps)

        query.prepare("SELECT filename FROM table_map WHERE id = ?")
        query.addBindValue(mapChosen)
        query.exec_()
        if query.size() > 0:
            query.first()
            mapname = str(query.value(0)).split("/")[1].replace(".zip", "")

        ngame = matchmakerGame(gameUuid, self)

        uuid = ngame.uuid
        
        #host is player 1
        
        ngame.setGameMap(mapname)
        ngame.setGameHostName(host.login)
        ngame.setGameHostUuid(host.id)
        ngame.setGameHostPort(host.gamePort)
        ngame.setGameHostLocalPort(host.gamePort)
        ngame.setGameName(gameName)

        place = 1
        for player in players1 :
            player.setGame(uuid)
            ngame.set_player_option(player.id, 'Team', 1)
            ngame.set_player_option(player.id, 'StartSpot', place)
            ngame.set_player_option(player.id, 'Color', place)
            ngame.set_player_option(player.id, 'Faction', player.faction)
            place += 2

        place = 2
        for player in players2 :
            player.setGame(uuid)
            ngame.set_player_option(player.id, 'Team', 2)
            ngame.set_player_option(player.id, 'StartSpot', place)
            ngame.set_player_option(player.id, 'Color', place)
            ngame.set_player_option(player.id, 'Faction', player.faction)
            place += 2

        #place the players
        for player in players1+players2 :
            if player != host:
                ngame.addPlayerToJoin(player)

        for player in players1:
            ngame.team1.append(player)

        for player in players2:
            ngame.team2.append(player)            


        ngame.numPlayers = len(players1+players2)
        ngame.maxPlayer = len(players1+players2)    

        self.addGame(ngame)

        
        #warn both players
        
        json = {}
        json["command"] = "game_launch"
        json["mod"] = self.gameTypeName
        json["mapname"] = str(mapname)
        json["reason"] = "ranked"
        json["uid"] = uuid
        #json["args"] = ["/players 2", "/team 1"]
        json["args"] = ["/players %i" % len(players1+players2), "/team 2", "/StartSpot 1", "/%s" % FACTIONS[host.getFaction()]]

        host.lobbyThread.sendJSON(json)
        

        for p in players1+players2:
            p.lobbyThread.sendJSON(dict(command="matchmaker_info", action="stopSearching"))

        
        self.manager.deleteTeam(teamuid)
        self.manager.deleteTeam(bestMatchupUid)
