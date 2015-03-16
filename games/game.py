# -------------------------------------------------------------------------------
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


from trueSkill.Team import *
from trueSkill.Teams import *
from time import time

from trueSkill.TrueSkill.FactorGraphTrueSkillCalculator import *
import uuid
import string
import logging

from .PlayerOptions import PlayerOptions

from PySide.QtSql import QSqlQuery

class GameState():
    def __init__(self):
        pass

    INITIALIZING = 0
    LOBBY = 1
    LIVE = 2

    @staticmethod
    def from_gpgnet_state(value):
        if value == 'Idle':
            return GameState.INITIALIZING
        if value == 'Lobby':
            return GameState.LOBBY
        if value == 'Launching':
            return GameState.LIVE


class Game(object):
    """
    Object that lasts for the lifetime of a game on FAF.
    """
    def __init__(self, uuid, parent=None, host=None, hostId=0, hostIp=None, hostLocalIp=None, hostPort=6112,
                 hostLocalPort=6112, state='Idle', gameName='None', map='SCMP_007', mode=0, minPlayer=1):
        """
        Initializes a new game
        :type uuid int
        :type host: None
        :type hostId: int
        :type hostIp: str
        :type hostLocalIp: str
        :type hostPort: int
        :type hostLocalPort: int
        :type state: str
        :type gameName: str
        :type map: str
        :type mode: int
        :type minPlayer: int
        :return: Game
        """
        self.createDate = time.time()
        self.receiveUdpHost = False
        self.log = logging.getLogger(__name__)
        self.uuid = uuid
        self.parent = parent
        self.ffa = False
        self.partial = 1
        self.access = "public"
        self.minPlayer = minPlayer
        self.maxPlayer = 12
        self.initMode = mode
        self.hostPlayer = host
        self.lobbyState = state
        self.hostuuid = hostId
        self.hostip = hostIp
        self.hostlocalip = hostLocalIp
        self.hostport = hostPort
        self.hostlocalport = hostLocalPort
        self.gameName = gameName
        self.mapName = map
        self.password = None
        self.players = []
        self.size = 0
        self.options = []
        self.modsVersion = {}
        self.gameType = 0
        self.AIs = []
        self.connections = {}
        self.packetReceived = {}
        self.desync = 0
        self.validGame = True
        self.invalidReason = None
        self.connecting = 0
        self.trueSkillPlayers = []
        self.teamAssign = {}
        self.playerPosition = {}
        self.teams = []
        self.finalTeams = []
        self.gameScore = {}
        self.gameResult = {}
        self.gameFaResult = {}
        self.playerFaction = {}
        self.playerColor = {}
        self._playerOptions = PlayerOptions()
        self.state = GameState.from_gpgnet_state(state)

        self.gameOptions = {'FogOfWar': 'explored', 'GameSpeed': 'normal', 'CheatsEnabled': 'false',
                            'PrebuiltUnits': 'Off', 'NoRushOption': 'Off', 'RestrictedCategories': 0}

        self.mods = []

    def add_game_connection(self, player: Player, game_connection):
        """
        Add a player with his associated connection to this game
        :param player:
        :param game_connection:
        :return:
        """
        pass

    def remove_game_connection(self, player: Player, game_connection):
        """
        Remove a player with his associated connection from this game
        :param peer:
        :param
        :return: None
        """
        pass

    def setPlayerOption(self, slot, key, value):
        if key == 'Faction':
            self.setPlayerFaction(slot, value)
        elif key == 'Color':
            self.setPlayerColor(slot, value)
        else:
            self._playerOptions[slot][key] = value

    def getPlayerOption(self, slot, key):
        try:
            if key == 'Faction':
                return self.getPlayerFaction(slot)
            elif key == 'Color':
                return self.getPlayerColor(slot)
            else:
                return self._playerOptions[slot][key]
        except KeyError:
            return None

    def getSimMods(self):
        return self.mods

    def getPlayerName(self, player):
        return player.getLogin()

    def getMaxPlayers(self):
        return self.maxPlayer

    def getOptions(self):
        return self.options

    def setAccess(self, access):
        self.access = access

    def getAccess(self):
        return self.access

    def setPassword(self, password):
        self.password = password

    def getPassword(self):
        return self.password


    def getGameType(self):
        return self.gameType

    def getGamemodVersion(self):
        return self.parent.getGamemodVersion()


    def setGameType(self, type):
        if type == "demoralization":
            self.gameType = 0
        elif type == "domination":
            self.gameType = 1
        elif type == "eradication":
            self.gameType = 2
        elif type == "sandbox":
            self.gameType = 3

    def getGamemod(self):
        return self.parent.getGameTypeName()

    def addAI(self, name):
        self.AIs.append(name)

    def clearAIs(self):
        for AI in self.AIs:
            self.placePlayer(AI, None)
            self.removePlayerFromAllTeam(AI)
            self.removeTrueSkillAI(AI)

        self.AIs = []

    def checkNoScore(self):
        for player in self.getPlayers():
            if not player in self.gameResult:
                #if the player don't register, chances are that he died or something
                self.gameResult[player] = -1

    def checkScore(self, player):
        if not player in self.gameResult:
            self.gameResult[player] = -1
        return

    def isValid(self):
        return self.validGame

    def getInvalidReason(self):
        return self.invalidReason

    def addDesync(self):
        self.desync = self.desync + 1

    def setInvalid(self, reason):
        self.validGame = False
        self.invalidReason = reason

    def getDesync(self):
        return self.desync

    def getuuid(self):
        return self.uuid

    def specialInit(self, player):
        self.placePlayer(player.getLogin(), -1)
        self.assignPlayerToTeam(player.getLogin(), -1)


    def specialEnding(self, logger, db, players):
        pass


    def isWinner(self, name):
        return 0

    def trueSkillUpdate(self, tsresults, tsplayers, logger, db, players, playerFnc="setRating", table="global_rating",
                        winner=False, sendScore=True):


        logger.debug("TS Results")

        noHumanResult = False
        if len(self.AIs) > 0:
            noHumanResult = True


        #sending to players
        for playerTS in tsplayers:


            name = playerTS.getPlayer()
            nameAI = None
            AI = False

            if str(name) in self.AIs:
                logger.debug("This is an AI")
                nameAI = str(name).rstrip(string.digits)
                AI = True

            logger.debug(name)
            logger.debug("original score")
            logger.debug(playerTS.getRating())
            origScore = playerTS.getRating()
            # if we got a result... Something bad can happens
            if tsresults != 0:
                # if the player was really in a playing team 
                if str(name) in tsresults.getAllPlayersNames():
                    logger.debug("player in game TrueSkill")

                    mean = (tsresults.getRating(name).getMean() * self.partial) + (
                        playerTS.getRating().getMean() * (1 - self.partial))
                    dev = (tsresults.getRating(name).getStandardDeviation() * self.partial) + (
                        playerTS.getRating().getStandardDeviation() * (1 - self.partial))

                    resPlayer = tsresults.getRating(name)
                    resPlayer.setMean(mean)
                    resPlayer.setStandardDeviation(dev)

                    logger.debug(resPlayer)

                    # Now we write the result in the DB. If player has already disconnect, it will update his score 
                    # no matter what.

                    #db.open()
                    query = QSqlQuery(db)

                    if winner:
                        if self.isWinner(name):
                            queryStr = (
                                           "UPDATE %s set mean =%f, deviation = %f, numGames = (numGames +1), winGames = (winGames +1) WHERE id = (SELECT id FROM login WHERE login.login = '%s')") % (
                                           table, mean, dev, str(name))
                            query.exec_(queryStr)
                        else:
                            queryStr = (
                                           "UPDATE %s set mean =%f, deviation = %f, numGames = (numGames +1) WHERE id = (SELECT id FROM login WHERE login.login = '%s')") % (
                                           table, mean, dev, str(name))
                            query.exec_(queryStr)

                    else:
                        if AI:
                            queryStr = (
                                           "UPDATE AI_rating set mean =%f, deviation = %f, numGames = (numGames +1) WHERE id = (SELECT id FROM AI_names WHERE AI_names.login = '%s')") % (
                                           mean, dev, nameAI)
                            query.exec_(queryStr)
                            gameId = self.getuuid()
                            queryStr = (
                                           "UPDATE game_player_stats set `after_mean` = %f, `after_deviation` = %f WHERE `gameId` = %s AND `playerId` = (SELECT id FROM AI_names WHERE login = '%s' )") % (
                                           mean, dev, str(gameId), nameAI)
                            logger.debug(queryStr)

                        else:
                            if noHumanResult == False:
                                queryStr = (
                                               "UPDATE %s set mean =%f, deviation = %f, numGames = (numGames +1) WHERE id = (SELECT id FROM login WHERE login.login = '%s')") % (
                                               table, mean, dev, str(name))
                                query.exec_(queryStr)
                                gameId = self.getuuid()
                                queryStr = (
                                               "UPDATE game_player_stats set `after_mean` = %f, `after_deviation` = %f WHERE `gameId` = %s AND `playerId` = (SELECT id FROM login WHERE login = '%s' )") % (
                                               mean, dev, str(gameId), str(name))
                                logger.debug(queryStr)
                                query.exec_(queryStr)
                    #logger.debug(queryStr) 

                    #db.close()
                    # if the player is still online, we update his rating
                    if noHumanResult == False:
                        for player in players.getAllPlayers():
                            if str(player.getLogin()) == str(name):
                                logger.debug("found player online")
                                function = getattr(player, playerFnc)
                                function(resPlayer)
                                break

                                # and we send the score

                        if sendScore:
                            results = self.getAllResults()
                            self.sendMessageToPlayers(players, name, results)
                    else:
                        if sendScore:
                            self.sendMessageToPlayers(players, name, "AI detected in game - No rating for humans.")

            else:
                logger.debug("ERROR : No Valid TS results !")

    def sendMessageToPlayers(self, players, name, message):
        for player in players.getAllPlayers():

            if str(player.getLogin()) == str(name):
                lobby = player.getLobbyThread()
                try:
                    if type(message) == list:
                        for part in message:
                            lobby.sendJSON(dict(command="notice", style="scores", text=str(part)))

                    else:
                        lobby.sendJSON(dict(command="notice", style="scores", text=str(message)))

                except:
                    pass

                break

    def getInitMode(self):
        return self.initMode


    def isAllScoresThere(self):
        if len(self.gameFaResult) != self.numPlayers or len(self.gameResult) != self.numPlayers:
            return False

        foundAVictory = False
        for player in self.gameFaResult:
            if self.gameFaResult[player] == "score":
                return False
            if self.gameFaResult[player] == "victory" or self.gameFaResult[player] == "draw":
                foundAVictory = True
        return foundAVictory

    def getAllResults(self):
        final = []
        msg = 'GAME RESULTS : \n'
        teamsResults = {}
        i = 1
        for teams in self.finalTeams:
            curScore = 0
            for players in teams.getAllPlayers():
                id = str(players.getId())
                if id in str(self.gameResult):
                    resultPlayer = self.gameResult[str(id)]
                    curScore = curScore + resultPlayer
                else:
                    return 0
            teamsResults[i] = curScore
            i = i + 1
        winnerTeam = None
        draw = False

        for team in teamsResults:
            if not winnerTeam:
                winnerTeam = team
            elif teamsResults[team] > teamsResults[winnerTeam]:
                winnerTeam = team
            elif teamsResults[team] == teamsResults[winnerTeam]:
                draw = True

        if winnerTeam:
            i = 1
            for teams in self.finalTeams:
                memTeam = []
                for players in teams.getAllPlayers():
                    id = str(players.getId())
                    memTeam.append(id)
                msg = msg + "Team " + str(i) + " ("
                members = ", ".join(memTeam)
                msg = msg + members + ") : "

                if draw:
                    msg = msg + "Draw \n"
                elif i == winnerTeam:
                    msg = msg + "Win \n"
                else:
                    msg = msg + "Lost \n"
                i += 1

        tsresults = self.computeResults(False)
        if tsresults != 0:
            msg += "\nNew ratings :\n"

            for playerTS in self.getTrueSkillPlayers():
                name = playerTS.getPlayer()
                if str(name) in tsresults.getAllPlayersNames():
                    mean = (tsresults.getRating(name).getMean() * self.partial) + (
                        playerTS.getRating().getMean() * (1 - self.partial))
                    dev = (tsresults.getRating(name).getStandardDeviation() * self.partial) + (
                        playerTS.getRating().getStandardDeviation() * (1 - self.partial))

                    msg = msg + name.getId() + ' : from ' + str(
                        int(playerTS.getRating().getConservativeRating())) + ' to ' + str(int(mean - 3 * dev)) + "\n"

        final.append(msg)
        return final


    def computeResults(self, update=True):
        self.log.debug("Computing results")
        if update:
            self.updateTrueskill()

        results = []
        for teams in self.finalTeams:
            curScore = 0
            for players in teams.getAllPlayers():
                id = str(players.getId())
                if id in str(self.gameResult):
                    resultPlayer = self.gameResult[str(id)]
                    curScore = curScore + resultPlayer
                else:
                    return 0
            results.append(curScore)
        gameInfo = GameInfo()
        calculator = FactorGraphTrueSkillCalculator()
        try:
            newRatings = calculator.calculateNewRatings(gameInfo, self.finalTeams, results)
            return newRatings
        except:
            return 0


    def addScorePlayer(self, player, score):
        self.gameScore[player] = score


    def addResultPlayer(self, player, faresult, score):
        if player in self.gameFaResult:
            if self.gameFaResult[player] != "victory":
                # the play got not decicive result yet, so we can apply it.
                self.gameFaResult[player] = faresult
                self.gameResult[player] = score


        else:
            self.gameFaResult[player] = faresult
            self.gameResult[player] = score

        return

    def getResultPlayers(self):
        return self.gameResult


    def returnKeyIndex(self, list, value):
        for d in list:
            if value in list[d]:
                return d
        return None

    def getPlayerFaction(self, player):
        if player in self.playerFaction:
            return self.playerFaction[player]

    def setPlayerFaction(self, player, faction):
        self.playerFaction[player] = faction

    def getPlayerColor(self, player):
        if player in self.playerColor:
            return self.playerColor[player]

    def setPlayerColor(self, player, color):
        self.playerColor[player] = color

    def placePlayer(self, player, position):
        # check if the player is already somewhere
        key = self.returnKeyIndex(self.playerPosition, player)
        # if so, delete his old place.
        if key is not None:
            del self.playerPosition[key]

        if position is not None:
            self.playerPosition[position] = str(player)

    def isAI(self, name):
        if name in self.AIs:
            return True
        else:
            return False

    def fixArray(self, array):
        playerPositionDef = {}
        i = 1
        for pos in sorted(array.keys()):
            if pos != -1:
                if self.isPlayerInGame(array[pos]) or self.isAI(array[pos]):
                    playerPositionDef[i] = array[pos]
                    i = i + 1
            else:
                #if pos = 1, team is -1 too
                self.assignPlayerToTeam(array[pos], -1)
        return playerPositionDef

    def fixPlayerPosition(self):
        self.playerPosition = self.fixArray(self.playerPosition)

    def getPlayerAtPosition(self, position):
        if position in self.playerPosition:
            return self.playerPosition[position]
        return None

    def getPositionOfPlayer(self, player):
        for pos in self.playerPosition:
            if self.playerPosition[pos] == player:
                return pos
        return -1

    def permutations(self, items):
        """Yields all permutations of the items."""
        if items == []:
            yield []
        else:
            for i in range(len(items)):
                for j in self.permutations(items[:i] + items[i + 1:]):
                    yield [items[i]] + j

    def getTeamsCount(self):
        result = 0
        for team in self.teamAssign:
            if len(self.teamAssign[team]) != 0:
                if team != 0:
                    result += 1
        return result

    def getBestMatchup(self):
        # Getting number of current teams
        nTeams = self.getTeamsCount()
        if nTeams == 0:
            return "No teams formed yet"
        gameInfo = GameInfo()
        calculator = FactorGraphTrueSkillCalculator()

        if len(self.trueSkillPlayers) % nTeams:
            return "Missing players for this number of teams (%i)" % (int(nTeams))

        platoon = len(self.trueSkillPlayers) / nTeams

        matchs = []
        for perm in list(self.permutations(self.trueSkillPlayers)):
            match = []
            for j in range(nTeams):
                team = []
                for i in range(platoon):
                    index = i + platoon * j
                    team.append(perm[index])
                team = sorted(team)
                match.append(team)
            matchs.append(match)

        a = []

        matchQuality = 0
        winningTeam = None

        for item in matchs:
            if not item[0] in a:
                a.append(item[0])

                Teams = []
                for i in range(nTeams):
                    resultTeam = Team()
                    for j in range(len(item[i])):

                        for player in item[i][j].getAllPlayers():
                            resultTeam.addPlayer(player, item[i][j].getRating())

                    Teams.append(resultTeam)

                curQual = calculator.calculateMatchQuality(gameInfo, Teams)
                if curQual > matchQuality:
                    matchQuality = curQual
                    winningTeam = Teams

        msg = "The best composition for teams is \n"

        for teams in winningTeam:
            msg = msg + 'team %i' % i + '\n'

            for player in teams.getAllPlayers():
                msg = msg + "player " + str(player.getId()) + "(" + str(teams.getRating(player)) + ")\n"
            i = i + 1

        msg = msg + "Game Quality : " + str(matchQuality * 100) + '%'
        return msg

    def getMatchQuality(self):
        try:
            gameInfo = GameInfo()
            calculator = FactorGraphTrueSkillCalculator()
            return calculator.calculateMatchQuality(gameInfo, self.finalTeams)
        except:
            return None

    def updateTrueskill(self):
        ''' Update all scores from the DB before updating the results'''
        self.log.debug("updating ratings")
        try:
            for team in self.finalTeams:
                for member in team.getAllPlayers():
                    query = QSqlQuery(self.parent.db)
                    query.prepare(
                        "SELECT mean, deviation FROM global_rating WHERE id = (SELECT id FROM login WHERE login = ?)")
                    query.addBindValue(member.getId())
                    query.exec_()
                    self.log.debug("updating a player")
                    if query.size() > 0:
                        query.first()
                        team.getRating(member).setMean(query.value(0))
                        team.getRating(member).setStandardDeviation(query.value(1))
                    else:
                        self.log.debug("error updating a player")
                        self.log.debug(member.getId())
        except:
            self.log.exception("Something awful happened while updating trueskill!")


    def recombineTeams(self):

        try:
            teamsRecomb = []
            for team in self.teamAssign:
                if team != -1:
                    if len(self.teamAssign[team]) != 0:
                        if team == 0:
                            for player in self.teamAssign[team]:
                                if self.getPositionOfPlayer(player) != -1:
                                    curTeam = Team()
                                    for playerTS in self.trueSkillPlayers:
                                        if str(playerTS.getPlayer()) == str(player):
                                            curTeam.addPlayer(playerTS.getPlayer(), playerTS.getRating())
                                            teamsRecomb.append(curTeam)
                        else:
                            curTeam = Team()
                            for player in self.teamAssign[team]:
                                if self.getPositionOfPlayer(player) != -1:
                                    for playerTS in self.trueSkillPlayers:
                                        if str(playerTS.getPlayer()) == str(player):
                                            curTeam.addPlayer(playerTS.getPlayer(), playerTS.getRating())
                            teamsRecomb.append(curTeam)

            self.finalTeams = teamsRecomb

            return self.finalTeams
        except:
            self.log.exception("Something awful happened in a recombing function!")


    def removePlayerFromAllTeam(self, name):
        for curTeam in self.teamAssign:
            if name in self.teamAssign[curTeam]:
                self.teamAssign[curTeam].remove(name)

    def assignPlayerToTeam(self, name, team):
        #remove him from others teams :
        for curTeam in self.teamAssign:
            if team != curTeam:
                if name in self.teamAssign[curTeam]:
                    self.teamAssign[curTeam].remove(name)

        if team in self.teamAssign:
            #check if we dont assign him twice !
            if not name in self.teamAssign[team]:
                self.teamAssign[team].append(name)
        else:
            list = []
            list.append(name)
            self.teamAssign[team] = list

        return 1

        return 0  #AI


    def getTeamsAssignements(self):
        return self.teamAssign


    def getTrueSkillPlayers(self):
        return self.trueSkillPlayers

    def addTrueSkillPlayer(self, player):
        self.trueSkillPlayers.append(player)

    def removeTrueSkillAI(self, name):
        for team in self.trueSkillPlayers:
            if str(name) == str(team.getPlayer()):
                self.trueSkillPlayers.remove(team)
                return 1
        return 0

    def removeTrueSkillPlayer(self, player):
        for team in self.trueSkillPlayers:
            if str(player.getLogin()) == str(team.getPlayer()):
                self.trueSkillPlayers.remove(team)
                return 1
        return 0

    @property
    def created_at(self):
        """
        :rtype : time
        """
        return self.createDate


    def removeFromAllPlayersToConnect(self, playerToRemove):
        """Remove playerToRemove from all lists of connections"""
        # for all the players in the game
        for player in self.getPlayers():
            # if the player has a connection list
            if player.getLogin() in self.connections:
                # we should remove the leaving player of the connection list of that player
                self.removeFromConnect(player, playerToRemove)
        # We should also remove the connection list of that leaving player !
        if playerToRemove.getLogin() in self.connections:
            del self.connections[playerToRemove.getLogin()]

        if playerToRemove.getLogin() in self.packetReceived:
            del self.packetReceived[playerToRemove.getLogin()]

    def addPlayer(self, player):
        """Add a player to the game"""
        if player == '':
            return 0
        self.players.append(player)
        return 1

    def isPlayerInGame(self, player):
        for p in self.getPlayers():
            if player == p.getLogin():
                return True
        return False

    def removePlayer(self, player):
        """Remove a player from the game"""
        if player == '':
            return 0
        for curPlayer in self.players:
            if curPlayer.getLogin() == player.getLogin():
                self.players.remove(curPlayer)
                self.removePlayerFromAllTeam(player.getLogin())
                return 1

        return 0

    def setGameName(self, name):
        if name == '':
            return None
        else:
            self.gameName = name


    def setLobbyState(self, state):
        if state == '':
            return 0
        else:
            self.lobbyState = state

    def setHostIP(self, ip):
        if ip == '':
            return 0
        else:
            self.hostip = ip

    def setHostLocalIP(self, ip):
        if ip == '':
            return 0
        else:
            self.hostlocalip = ip


    def setGameMap(self, map):
        if map == '':
            return False
        else:
            self.mapName = map

    def getGameMap(self):
        return self.mapName

    def setGameHostPort(self, port):
        if port == '':
            return 0
        else:
            self.hostport = port

    def setGameHostLocalPort(self, port):
        if port == '':
            return 0
        else:
            self.hostlocalport = port

    def setGameHostName(self, host):
        if host == '':
            return 0
        else:
            self.hostPlayer = host

    def setGameHostUuid(self, uuid):
        if uuid == '':
            return 0
        else:
            self.hostuuid = uuid

    def getGameAddress(self):
        return "%s:%s" % (str(self.getHostIp()), str(self.getHostPort()))

    def getGameLocalAddress(self):
        return "%s:%s" % (str(self.getHostLocalIp()), str(self.getHostLocalPort()))

    def getHostPort(self):
        return self.hostport

    def getHostLocalPort(self):
        return self.hostlocalport


    def getHostName(self):
        return self.hostPlayer

    def getHostId(self):
        return self.hostuuid

    def getGameName(self):
        return self.gameName

    def getHostIp(self):
        return self.hostip

    def getHostLocalIp(self):
        return self.hostlocalip

    def getLobbyState(self):
        return self.lobbyState

    def getPlayers(self):
        return self.players

    def getMinPlayers(self):
        return self.minPlayer

    def getMapName(self):
        return self.mapName

    def getNumPlayer(self):
        return len(self.players)
