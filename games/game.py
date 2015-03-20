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
from enum import Enum
import string
import logging
import time

from PySide.QtSql import QSqlQuery

from src.abc.base_game import GameConnectionState, BaseGame
from src.players import Player


class GameState(Enum):
    INITIALIZING = 0
    LOBBY = 1
    LIVE = 2
    ENDED = 3

    @staticmethod
    def from_gpgnet_state(value):
        if value == 'Idle':
            return GameState.INITIALIZING
        if value == 'Lobby':
            return GameState.LOBBY
        if value == 'Launching':
            return GameState.LIVE


class GameError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class Game(BaseGame):
    """
    Object that lasts for the lifetime of a game on FAF.
    """
    def __init__(self, uuid, parent, host=None, hostId=0, hostIp=None, hostLocalIp=None, hostPort=6112,
                 hostLocalPort=6112, gameName='None', map='SCMP_007', mode=0, minPlayer=1):
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
        self.db = parent.db
        self.parent = parent
        self._player_options = {}
        self.createDate = time.time()
        self.receiveUdpHost = False
        self._logger = logging.getLogger("{}.{}".format(self.__class__.__qualname__, uuid))
        self.uuid = uuid
        self.ffa = False
        self.partial = 1
        self.access = "public"
        self.minPlayer = minPlayer
        self.maxPlayer = 12
        self.initMode = mode
        self.hostPlayer = host
        self.hostuuid = hostId
        self.hostip = hostIp
        self.hostlocalip = hostLocalIp
        self.hostport = hostPort
        self.hostlocalport = hostLocalPort
        self.gameName = gameName
        self.mapName = map
        self.password = None
        self._players = []
        self.size = 0
        self.options = []
        self.modsVersion = {}
        self.gameType = 0
        self.AIs = []
        self.packetReceived = {}
        self.desync = 0
        self.validGame = True
        self.invalidReason = None
        self.connecting = 0
        self.trueSkillPlayers = []
        self.teamAssign = {}
        self.playerPosition = {}
        self.finalTeams = []
        self.gameScore = {}
        self.gameResult = {}
        self.gameFaResult = {}
        self.playerFaction = {}
        self.playerColor = {}
        self.state = GameState.INITIALIZING
        self._connections = {}
        self.gameOptions = {'FogOfWar': 'explored', 'GameSpeed': 'normal', 'CheatsEnabled': 'false',
                            'PrebuiltUnits': 'Off', 'NoRushOption': 'Off', 'RestrictedCategories': 0}

        self.mods = []
        self._logger.info("{} created".format(self))

    @property
    def players(self):
        """
        Players in the game

        Depending on the state, it is either:
          - (LOBBY) The currently connected players
          - (LIVE) Players who participated in the game
          - Empty list
        :return: set
        """
        if self.state == GameState.LIVE:
            return self._players
        elif self.state == GameState.LOBBY:
            return set(self._connections.keys())
        else:
            return []

    @property
    def id(self):
        return self.uuid

    @property
    def teams(self):
        return dict([(team, [player for player in self.players if player.team == team])
                for team in set([player.team for player in self.players])])

    def add_game_connection(self, game_connection):
        """
        Add a game connection to this game
        :param game_connection:
        :return:
        """
        if game_connection.state != GameConnectionState.connected_to_host:
            raise GameError("Invalid GameConnectionState: {}".format(game_connection.state))
        self._logger.info("Added game connection {}".format(game_connection))
        self._connections[game_connection.player] = game_connection

    def remove_game_connection(self, game_connection):
        """
        Remove a game connection from this game

        Will trigger on_game_end if there are no more active connections to the game
        :param peer:
        :param
        :return: None
        """
        del self._connections[game_connection.player]
        self._logger.info("Removed game connection {}".format(game_connection))
        if len(self._connections) == 0:
            self.on_game_end()

    def on_game_end(self):
        self._logger.info("Game ended")
        query = QSqlQuery(self.db)
        queryStr = ("UPDATE game_stats set `EndTime` = NOW() where `id` = " + str(self.id))
        query.exec_(queryStr)
        self.rate_game()

    def set_player_option(self, player, key, value):
        if player not in self._player_options:
            self._player_options[player] = {}
        self._player_options[player][key] = value

    def get_player_option(self, player, key):
        try:
            return self._player_options[player][key]
        except KeyError:
            return None

    def launch(self):
        """
        Mark the game as live.

        Freezes the set of active players so they are remembered if they drop.
        :return: None
        """
        assert self.state == GameState.LOBBY
        self._players = self.players
        self.state = GameState.LIVE
        self._logger.info("Game launched")

    def setAccess(self, access):
        self.access = access

    def setPassword(self, password):
        self.password = password

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
        return self.parent.gameTypeName

    def addAI(self, name):
        self.AIs.append(name)

    def clearAIs(self):
        for AI in self.AIs:
            self.placePlayer(AI, None)
            self.removePlayerFromAllTeam(AI)
            self.removeTrueSkillAI(AI)

        self.AIs = []

    def checkNoScore(self):
        for player in self.players:
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
        self.desync += 1

    def setInvalid(self, reason):
        self.validGame = False
        self.invalidReason = reason

    def specialInit(self, player):
        self.placePlayer(player.getLogin(), -1)
        self.assignPlayerToTeam(player.getLogin(), -1)

    def trueSkillUpdate(self, tsresults, tsplayers, logger, db, players, playerFnc="setRating", table="global_rating",
                        winner=False, sendScore=True):

        noHumanResult = False
        if len(self.AIs) > 0:
            noHumanResult = True

        for playerTS in tsplayers:
            name = playerTS.getPlayer()
            nameAI = None
            AI = False
            if str(name) in self.AIs:
                logger.debug("This is an AI")
                nameAI = str(name).rstrip(string.digits)
                AI = True
            if tsresults != 0:
                # if the player was really in a playing team 
                if str(name) in tsresults.playersNames():
                    mean = (tsresults.getRating(name).getMean() * self.partial) + (
                        playerTS.getRating().getMean() * (1 - self.partial))
                    dev = (tsresults.getRating(name).getStandardDeviation() * self.partial) + (
                        playerTS.getRating().getStandardDeviation() * (1 - self.partial))

                    resPlayer = tsresults.getRating(name)
                    resPlayer.setMean(mean)
                    resPlayer.setStandardDeviation(dev)

                    query = QSqlQuery(db)

                    if winner:
                        query.prepare("UPDATE %s set mean = ?, deviation = ?, numGames = (numGames + 1) WHERE id = (SELECT id FROM login WHERE login.login = ?)" % table)
                        query.addBindValue(mean)
                        query.addBindValue(dev)
                        query.addBindValue(str(name))
                        query.exec_()
                        query.finish()
                    else:
                        if AI:
                            query.prepare("UPDATE AI_rating set mean = ?, deviation = ?, numGames = (numGames +1) WHERE id = (SELECT id FROM AI_names WHERE AI_names.login = ?)")
                            query.addBindValue(mean)
                            query.addBindValue(dev)
                            query.addBindValue(nameAI)
                            query.exec_()
                            query.finish()

                            query.prepare("UPDATE game_player_stats set `after_mean` = ?, `after_deviation` = ? WHERE `gameId` = ? AND `playerId` = (SELECT id FROM AI_names WHERE login = ?)")
                            query.addBindValue(mean)
                            query.addBindValue(dev)
                            query.addBindValue(str(self.uuid))
                            query.addBindValue(nameAI)
                            query.exec_()
                            query.finish()
                        else:
                            if not noHumanResult:
                                query.prepare("UPDATE %s set mean = ?, deviation = ?, numGames = (numGames +1) WHERE id = (SELECT id FROM login WHERE login.login = ?)" % table)
                                query.addBindValue(mean)
                                query.addBindValue(dev)
                                query.addBindValue(str(name))
                                query.exec_()
                                query.finish()

                                query.prepare("UPDATE game_player_stats set `after_mean` = ?, `after_deviation` = ? WHERE `gameId` = ? AND `playerId` = (SELECT id FROM AI_names WHERE login = ?)")
                                query.addBindValue(mean)
                                query.addBindValue(dev)
                                query.addBindValue(str(self.uuid))
                                query.addBindValue(str(name))
                                query.exec_()
                                query.finish()

                    # if the player is still online, we update his rating
                    if not noHumanResult:
                        for player in players.players():
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
                logger.debug("ERROR: No Valid TS results!")

    def sendMessageToPlayers(self, players, name, message):
        for player in players.players():

            if str(player.getLogin()) == str(name):
                lobby = player.lobbyThread
                try:
                    if type(message) == list:
                        for part in message:
                            lobby.sendJSON(dict(command="notice", style="scores", text=str(part)))

                    else:
                        lobby.sendJSON(dict(command="notice", style="scores", text=str(message)))

                except:
                    pass

                break

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
            for players in teams.players():
                id = str(players.getId())
                if id in str(self.gameResult):
                    resultPlayer = self.gameResult[str(id)]
                    curScore = curScore + resultPlayer
                else:
                    return 0
            teamsResults[i] = curScore
            i += 1
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
                for players in teams.players():
                    id = str(players.getId())
                    memTeam.append(id)
                msg = msg + "Team " + str(i) + " ("
                members = ", ".join(memTeam)
                msg = msg + members + ") : "

                if draw:
                    msg += "Draw \n"
                elif i == winnerTeam:
                    msg += "Win \n"
                else:
                    msg += "Lost \n"
                i += 1

        tsresults = self.computeResults(False)
        if tsresults != 0:
            msg += "\nNew ratings :\n"

            for playerTS in self.trueSkillPlayers:
                name = playerTS.getPlayer()
                if str(name) in tsresults.playersNames():
                    mean = (tsresults.getRating(name).getMean() * self.partial) + (
                        playerTS.getRating().getMean() * (1 - self.partial))
                    dev = (tsresults.getRating(name).getStandardDeviation() * self.partial) + (
                        playerTS.getRating().getStandardDeviation() * (1 - self.partial))

                    msg = msg + name.getId() + ' : from ' + str(
                        int(playerTS.getRating().getConservativeRating())) + ' to ' + str(int(mean - 3 * dev)) + "\n"

        final.append(msg)
        return final


    def computeResults(self, update=True):
        self._logger.debug("Computing results")
        if update:
            self.updateTrueskill()

        results = []
        for teams in self.finalTeams:
            curScore = 0
            for players in teams.players():
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
                    i += 1
            else:
                #if pos = 1, team is -1 too
                self.assignPlayerToTeam(array[pos], -1)
        return playerPositionDef

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

    def updateTrueskill(self):
        """ Update all scores from the DB before updating the results"""
        self._logger.debug("updating ratings")
        try:
            for team in self.finalTeams:
                for member in team.players():
                    query = QSqlQuery(self.db)
                    query.prepare(
                        "SELECT mean, deviation FROM global_rating WHERE id = (SELECT id FROM login WHERE login = ?)")
                    query.addBindValue(member.getId())
                    query.exec_()
                    self._logger.debug("updating a player")
                    if query.size() > 0:
                        query.first()
                        team.getRating(member).setMean(query.value(0))
                        team.getRating(member).setStandardDeviation(query.value(1))
                    else:
                        self._logger.debug("error updating a player")
                        self._logger.debug(member.getId())
        except:
            self._logger.exception("Something awful happened while updating trueskill!")


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
            self._logger.exception("Something awful happened in a recombing function!")


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
            self.teamAssign[team] = [name]

        return 1

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
        for player in self.players:
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
        for p in self.players:
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
        return "%s:%s" % (str(self.hostip), str(self.hostport))

    def getGameLocalAddress(self):
        return "%s:%s" % (str(self.hostlocalip), str(self.hostlocalport))

    def __str__(self):
        return "Game({})".format(self.uuid)
