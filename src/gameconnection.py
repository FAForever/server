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
# -------------------------------------------------------------------------------

import asyncio
import string
import time
import json
import logging

from PySide import QtNetwork
from PySide.QtNetwork import QTcpSocket, QAbstractSocket
from PySide.QtSql import *

from src.abc.base_game import GameConnectionState
from src.connectivity import TestPeer, Connectivity
from games.game import Game, GameState
from src.decorators import with_logger, timed
from src.games_service import GamesService
from src.protocol.gpgnet import GpgNetServerProtocol
from src.subscribable import Subscribable


logger = logging.getLogger(__name__)

from proxy import proxy

from src.JsonTransport import QDataStreamJsonTransport

from config import Config

proxyServer = QtNetwork.QHostAddress("127.0.0.1")

@with_logger
class GameConnection(Subscribable, GpgNetServerProtocol):
    """
    Responsible for the games protocol.
    """

    def __init__(self, loop, users, games: GamesService, db, server):
        Subscribable.__init__(self)
        self._state = GameConnectionState.initializing
        self.loop = loop
        self.users = users
        self.games = games

        self.db = db
        self.log = logging.getLogger(__name__)
        self.initTime = time.time()
        self.initDone = False
        self.proxies = {}
        self._player = None
        self.logGame = "\t"
        self._game = None
        self.proxyConnection = []

        self.last_pong = time.time()

        self.player = None
        self._socket = None
        self.lobby = None
        self.transport = None
        self.nat_packets = {}
        self.ping_task = None

        self.connectivity_state = asyncio.Future()

    @property
    def state(self):
        return self._state

    @property
    def game(self):
        """
        :rtype: Game
        """
        return self._game

    @game.setter
    def game(self, value):
        self._game = value

    def accept(self, socket):
        """
        Accept a connected socket for this GameConnection

        Will look up the user using the provided users service
        :param socket: An initialised socket
        :type socket QTcpSocket
        :raise AssertionError
        :return: bool
        """
        assert socket.isValid()
        assert socket.state() == QAbstractSocket.ConnectedState
        self.log.debug("Accepting connection from %r" % socket.peerAddress())
        self._socket = socket
        self._socket.setSocketOption(QTcpSocket.KeepAliveOption, 1)
        self._socket.disconnected.connect(self.disconnection)
        self._socket.error.connect(self.on_error)
        self._socket.stateChanged.connect(self.on_socket_state_change)

        self.transport = QDataStreamJsonTransport(self._socket)
        self.transport.messageReceived.connect(self.handleAction2)

        self.lobby = None
        ip = self._socket.peerAddress().toString()
        port = self._socket.peerPort()
        self.player = self.users.findByIp(ip)
        self.log.debug("Resolved user to {} through lookup by {}:{}".format(self.player, ip, port))

        if self.player is None:
            self._socket.abort()
            self.log.info("Player not found for IP: %s " % ip)
            return False

        self.player.gameThread = self
        # reset the udpPacket from server state

        self.player.setPort = False
        self.player.connectedToHost = False


        self.lobby = self.player.lobbyThread

        strlog = ("%s\t" % str(self.player.getLogin()))
        self.logGame = strlog

        self.ping_task = asyncio.async(self.ping())
        self.player.wantToConnectToGame = False
        self._state = GameConnectionState.initialized
        return True

    def sendToRelay(self, action, commands):
        message = {"key": action, "commands": commands}
        self.transport.send_message(message)

    @asyncio.coroutine
    def ping(self):
        """
        Ping the relay server to check if the player is still there.
        """
        while True:
            if time.time() - self.last_pong > 30:
                self.log.debug("{} Missed ping - removing player {}"
                               .format(self.logGame, self._socket.peerAddress().toString()))
                self.abort()
            self.send_Ping()
            yield from asyncio.sleep(20)

    def _handle_idle_state(self):
        """
        This message is sent by FA when it doesn't know what to do.
        :return: None
        """
        self._game = self.games.find_by_id(self.player.getGame())
        assert self.game
        self.game.add_game_connection(self)
        self.send_Ping()
        action = self.player.getAction()

        if action == "HOST":
            self.game.state = GameState.INITIALIZING
            self.game.setHostIP(self.player.getIp())
            self.game.setHostLocalIP(self.player.getLocalIp())
            self.game.proxy = proxy.proxy()
            strlog = (
                "%s.%s.%s\t" % (str(self.player.getLogin()), str(self.game.uuid), str(self.game.getGamemod())))
            self.logGame = strlog
            self._send_create_lobby(self.game.initMode)

        elif action == "JOIN":
            strlog = (
                "%s.%s.%s\t" % (str(self.player.getLogin()), str(self.game.uuid), str(self.game.getGamemod())))
            self.logGame = strlog
            self._send_create_lobby(self.game.initMode)

        else:
            # We tell the lobby that FA must be killed.
            self.lobby.sendJSON(dict(command="notice", style="kill"))
            self.log.debug("QUIT - No player action :(")

    def abort(self):
        """
        Abort the connection, calling doEnd() first
        :return:
        """
        if self._state is GameConnectionState.aborted or self._state is GameConnectionState.ended:
            return
        self._state = GameConnectionState.aborted
        self.log.debug("{}.abort()".format(self))
        try:
            self.doEnd()
            self.player.lobbyThread.sendJSON(dict(command="notice", style="kill"))
        except Exception as ex:
            self.log.debug("Exception in abort(): {}".format(ex))
            pass
        finally:
            if self._socket is not None:
                self._socket.abort()
            if self.ping_task is not None:
                self.ping_task.cancel()
            del self._socket
            del self._player
            del self._game


    @asyncio.coroutine
    def _handle_lobby_state(self):
        """
        The game has told us it is ready and listening on
        self.player.gamePort for UDP.
        We determine the connectivity of the peer and respond
        appropriately
        """
        with TestPeer(self,
                      self.player.getIp(),
                      self.player.gamePort,
                      self.player.getId()) as peer_test:
            self._connectivity_state = yield from asyncio.async(peer_test.determine_connectivity())
            self.sendToRelay('ConnectivityState', [self.player.getId(),
                                                   self._connectivity_state.value])

        playeraction = self.player.getAction()
        if playeraction == "HOST":
            map = self.game.mapName
            self._send_host_game(str(map))
        # if the player is joining, we connect him to host.
        elif playeraction == "JOIN":
            yield from self.ConnectToHost(self.game.host.gameThread)

    @timed(limit=0.1)
    def handleAction2(self, action):
        """
        This code is starting to get messy...
        This function was created when the FA protocol was moved to the lobby itself
        """
        try:
            message = json.loads(action)
            message["command_id"] = message['action']
            message["arguments"] = message['chuncks']
            self.notify(message)
            asyncio.async(self.handle_action(message["action"], message["chuncks"]))
        except ValueError as ex:
            self.log.error("Garbage JSON {} {}".format(ex, action))

    def handle_ProcessServerNatPacket(self, message, host, port):
        self.log.debug("handle_ProcessServerNatPacket {}".format(self))
        self.notify({
            'command_id': 'ProcessServerNatPacket',
            'arguments': [host, port, message]
        })

    @asyncio.coroutine
    def ConnectToHost(self, peer):
        """
        Connect self to a given peer (host)
        :return:
        """
        assert peer.player.action == 'HOST'
        states = [peer.connectivity_state, self.connectivity_state]
        yield from asyncio.wait(states)
        peer_state = self.connectivity_state.result()
        if peer.connectivity_state.result() == Connectivity.PROXY or peer_state == Connectivity.PROXY:
            # TODO: revise if this is the right thing to do
            self.send_JoinGame(peer.player.address_and_port,
                               False,
                               peer.player.login,
                               peer.player.id)
            peer.ConnectThroughProxy(self)
        elif peer.connectivity_state.result() == Connectivity.PUBLIC:
            if peer_state == Connectivity.PUBLIC:
                self.send_JoinGame(peer.player.address_and_port,
                                   False,
                                   peer.player.login,
                                   peer.player.id)
                peer.send_ConnectToPeer(self.player.address_and_port, self.player.login, self.player.id)
            else:
                with peer.subscribe(peer, ['ProcessNatPacket']) as sub:
                    nat_message = "Hello {}".format(peer.player.id)
                    self.send_SendNatPacket(peer.player.address_and_port, nat_message)
                    yield from sub.wait_for('ProcessNatPacket', 2)
                    if nat_message in peer.nat_packets \
                            and peer.nat_packets[nat_message] == self.player.address_and_port:
                        self.send_JoinGame(peer.player.address_and_port,
                                           False,
                                           peer.player.login,
                                           peer.player.id)
                        peer.send_ConnectToPeer(self.player.address_and_port,
                                                self.player.login,
                                                self.player.id)
                    else:
                        # TODO: Fallback to proxying
                        pass

        elif peer.connectivity_state.result() == Connectivity.STUN:
            if peer_state == Connectivity.PUBLIC:
                with self.subscribe(peer, ['ProcessNatPacket']) as sub:
                    nat_message = "Hello {}".format(self.player.id)
                    peer.send_SendNatPacket(self.player.address_and_port, nat_message)
                    yield from sub.wait_for('ProcessNatPacket', 2)
                    if nat_message in peer.nat_packets.keys() \
                            and peer.nat_packets[nat_message] == self.player.address_and_port:
                        self.send_JoinGame(peer.nat_packets[nat_message],
                                           False,
                                           peer.player.login,
                                           peer.player.id)
                        peer.send_ConnectToPeer(self.player.address_and_port, self.player.login, self.player.id)
                    else:
                        # Peer isn't receiving our packets, even though they're meant to
                        # TODO: Fallback to proxy connection
                        pass
            else:
                # Perform STUN
                pass

    @asyncio.coroutine
    def ConnectToPeer(self, peer2: GpgNetServerProtocol):
        """
        Connect two peers
        :return: None
        """
        states = [self.connectivity_state, peer2.connectivity_state]
        yield from asyncio.wait(states)
        if self.connectivity_state == Connectivity.PUBLIC:
            if peer2.connectivity_state != Connectivity.PROXY:
                peer2.send_ConnectToPeer(self.player.ip, peer2.player.login, peer2.player.id)

    @asyncio.coroutine
    def handle_action(self, key, values):
        """
        Handle GpgNetSend messages, wrapped in the JSON protocol
        :param key: command type
        :param values: command parameters
        :type key str
        :type values list
        :return: None
        """
        self.log.debug("handle_action %s:%s" % (key, values))
        try:
            if key == 'ping':
                return

            elif key == 'Disconnected':
                return

            elif key == 'pong':
                self.last_pong = time.time()
                return

            elif key == 'Connected':
                pass  # This message is deprecated

            elif key == 'ConnectedToHost':
                pass  # This message is deprecated, since we tell players to connect to all peers at once

            elif key == 'Score':
                pass

            elif key == 'Bottleneck':
                # TODO: Use this for p2p reconnect
                pass

            elif key == 'BottleneckCleared':
                # TODO: Use this for p2p reconnect
                pass

            elif key == 'Desync':
                self.game.addDesync()

            elif key == 'ProcessNatPacket':
                pass

            elif key == 'GameState':
                state = values[0]
                yield from self.handle_game_state(state)

            elif key == 'GameOption':

                if values[0] in self.game.gameOptions:
                    self.game.gameOptions[values[0]] = values[1]

                if values[0] == "Slots":
                    self.game.maxPlayer = values[1]

                if values[0] == 'ScenarioFile':
                    raw = "%r" % values[1]
                    path = raw.replace('\\', '/')
                    map = str(path.split('/')[2]).lower()
                    curMap = self.game.mapName
                    if curMap != map:
                        self.game.setGameMap(map)
                        self.sendGameInfo()

                elif values[0] == 'Victory':
                    self.game.setGameType(values[1])

            elif key == 'GameMods':
                if values[0] == "activated":
                    if values[1] == 0:
                        self.game.mods = {}

                if values[0] == "uids":
                    self.game.mods = {}
                    query = QSqlQuery(self.db)
                    for uid in values[1].split():
                        query.prepare("SELECT name FROM table_mod WHERE uid = ?")
                        query.addBindValue(uid)
                        query.exec_()
                        if query.size() > 0:
                            query.first()
                            self.game.mods[uid] = str(query.value(0))
                        else:
                            self.game.mods[uid] = "Unknown sim mod"

            elif key == 'PlayerOption':
                if self.player.getAction() == "HOST":
                    id = values[0]
                    key = values[1]
                    value = values[2]
                    self.game.set_player_option(id, key, value)
                    self.sendGameInfo()

            elif key == 'GameResult':
                playerResult = self.game.getPlayerAtPosition(int(values[0]))
                if playerResult is not None:
                    result = values[1]
                    faresult = None
                    score = 0
                    if result.startswith("defeat")\
                       or result.startswith("victory")\
                       or result.startswith("score")\
                       or result.startswith("draw"):
                        split = result.split(" ")
                        faresult = split[0]
                        if len(split) > 1:
                            score = int(split[1])

                    self.game.addResultPlayer(playerResult, faresult, score)

                    if faresult != "score":
                        if hasattr(self.game, "noStats"):
                            if not self.game.noStats:
                                self.registerTime(playerResult)
                        else:
                            self.registerTime(playerResult)

            elif key == 'Stats':
                # TODO: Log these
                pass

            elif key == 'Chat':
                # TODO: Send this to IRC for the game?
                pass

            elif key == 'OperationComplete':
                if self.game.isValid():
                    mission = -1
                    if int(values[0]) == 1:
                        self.log.debug(self.logGame + "Operation really Complete!")
                        query = QSqlQuery(self.db)
                        query.prepare(
                            "SELECT id FROM coop_map WHERE filename LIKE '%/" + self.game.mapName + ".%'")
                        query.exec_()
                        if query.size() > 0:
                            query.first()
                            mission = int(query.value(0))
                        else:
                            self.log.debug(self.logGame + "can't find coop map " + self.game.mapName)
                    if mission != -1:

                        query.prepare(
                            "INSERT INTO `coop_leaderboard`(`mission`, `gameuid`, `secondary`, `time`) VALUES (?,?,?,?);")
                        query.addBindValue(mission)
                        query.addBindValue(self.game.uuid)
                        query.addBindValue(int(values[1]))
                        query.addBindValue(str(values[2]))
                        if not query.exec_():
                            self.log.warning(self.logGame + str(query.lastError()))
                            self.log.warning(self.logGame + query.executedQuery())
                else:
                    self.log.debug(self.logGame + self.game.getInvalidReason())

            elif key == 'ArmyCalled':
                # this is for Galactic War!
                playerResult = self.game.getPlayerAtPosition(int(values[0]))
                if playerResult is not None:
                    group = values[1]
                    query = QSqlQuery(self.db)
                    query.prepare(
                        "DELETE FROM `galacticwar`.`reinforcements_groups` WHERE `userId` = (SELECT id FROM `faf_lobby`.`login` WHERE login.login = ?) AND `group` = ?")
                    query.addBindValue(playerResult)
                    query.addBindValue(group)
                    if query.exec_():
                        self.game.deleteGroup(group, playerResult)

            else:
                pass
        except:
            self.log.exception(self.logGame + "Something awful happened in a game thread!")
            self.abort()

    def on_ProcessNatPacket(self, address_and_port, message):
        self.nat_packets[message] = address_and_port

    @asyncio.coroutine
    def handle_game_state(self, state):
        """
        Changes in game state
        :param state: new state
        :return: None
        """
        if state == 'Idle':
            # FA has just connected to us
            self._handle_idle_state()

        elif state == 'Lobby':
            # The game is initialized and awaiting commands
            # At this point, it is listening locally on the
            # port we told it to (self.player.gamePort)
            # We schedule an async task to determine their connectivity
            # and respond appropriately
            yield from asyncio.async(self._handle_lobby_state())

        elif state == 'Launching':
            # game launch, the user is playing !
            if self.player.getAction() == "HOST":
                self.game.launch()

                if hasattr(self.game, "noStats"):
                    if not self.game.noStats:
                        self.fillGameStats()
                else:
                    self.fillGameStats()

                self.game.fixPlayerPosition()

                self.fillPlayerStats(self.game.players)
                self.fillAIStats(self.game.AIs)
                for player in self.game.players:
                    player.setAction("PLAYING")

                if not all((i.count()) == self.game.finalTeams[0].count() for i in self.game.finalTeams):
                    self.game.setInvalid("All Teams don't the same number of players.")

                self.game.setTime()

                self.sendGameInfo()

                if self.game.gameType != 0 and self.game.getGamemod() != "coop":
                    self.game.setInvalid("Only assassination mode is ranked")

                elif self.game.gameOptions["FogOfWar"] != "explored":
                    self.game.setInvalid("Fog of war not activated")

                elif self.game.gameOptions["CheatsEnabled"] != "false":
                    self.game.setInvalid("Cheats were activated")

                elif self.game.gameOptions["PrebuiltUnits"] != "Off":
                    self.game.setInvalid("Prebuilt was activated")

                elif self.game.gameOptions["NoRushOption"] != "Off":
                    self.game.setInvalid("No rush games are not ranked")

                elif self.game.gameOptions["RestrictedCategories"] != 0:
                    self.game.setInvalid("Restricted games are not ranked")

                elif len(self.game.mods) > 0:
                    for uid in self.game.mods:
                        if not self.isModRanked(uid):
                            if uid == "e7846e9b-23a4-4b95-ae3a-fb69b289a585":
                                if not "scca_coop_e02" in self.game.mapName.lower():
                                    self.game.setInvalid("Sim mods are not ranked")

                            else:
                                self.game.setInvalid("Sim mods are not ranked")

                        query = QSqlQuery(self.db)
                        query.prepare("UPDATE `table_mod` SET `played`= `played`+1  WHERE uid = ?")
                        query.addBindValue(uid)
                        query.exec_()

                for playerTS in self.game.trueSkillPlayers:
                    if playerTS.getRating().getMean() < -1000:
                        self.game.setInvalid("You are playing with a smurfer.")

    def doEnd(self):
        ''' bybye player :('''
        self.game.remove_game_connection(self)
        if self._state is GameConnectionState.ended:
            return
        else:
            self._state = GameConnectionState.ended

        state = self.game.state
        if state == GameState.LIVE:
            curplayers = len(self.game.players)
            allScoreHere = False
            if hasattr(self.game, "isAllScoresThere"):
                allScoreHere = self.game.isAllScoresThere()

            if curplayers == 0 or allScoreHere:
                self.game.state = GameState.ENDED
                self.sendGameInfo()

                if hasattr(self.game, "noStats"):
                    if not self.game.noStats:
                        query = QSqlQuery(self.db)
                        queryStr = (
                            "UPDATE game_stats set `EndTime` = NOW() where `id` = " + str(
                                self.game.uuid))
                        query.exec_(queryStr)
                else:
                    query = QSqlQuery(self.db)
                    queryStr = (
                        "UPDATE game_stats set `EndTime` = NOW() where `id` = " + str(self.game.uuid))
                    query.exec_(queryStr)

                if self.game.desync > 20:
                    self.game.setInvalid("Too many desyncs")

                if hasattr(self.game, "noStats"):
                    if not self.game.noStats:
                        self.registerScore(self.game.gameResult)
                else:
                    self.registerScore(self.game.gameResult)

                for playerTS in self.game.trueSkillPlayers:
                    name = playerTS.getPlayer()
                    for player in self.listUsers.getAllPlayers():
                        if player is not None:
                            if str(name) == player.getLogin():
                                for conn in self.parent.parent.FALobby.recorders:
                                    conn.sendJSON(self.parent.parent.jsonPlayer(player))

                self.games.removeGame(self.game)
                self._game = None

        # if game in lobby state
        if state != GameState.LIVE:
            getAction = self.player.getAction()
            if getAction == "HOST":
                # if the player was the host (so, not playing), we remove his game
                self.game.state = GameState.ENDED
                self.sendGameInfo()
                self.games.removeGame(self.game)
                self._game = None

            elif getAction == 'JOIN':
                minplayers = self.game.minPlayer
                curplayers = len(self.game.players)
                if minplayers == 2 or curplayers == 0:
                    self.game.state = GameState.ENDED
                    self.sendGameInfo()
                    self.games.removeGame(self.game)
                    self._game = None
        # if the game was in play.
        else:
            self.sendGameInfo()

    def _send_create_lobby(self, rankedMode):
        """
        Used for initializing the game to start listening on UDP
        :param rankedMode int:
            If 1: The game uses autolobby.lua
               0: The game uses lobby.lua
        :return: None
        """
        if self.game is None:
            text = "You were unable to connect to the host because he has left the game."
            self.lobby.sendJSON(dict(command="notice", style="kill"))
            self.lobby.sendJSON(dict(command="notice", style="info", text=str(text)))
            self.abort()
            return

        port = self.player.gamePort
        login = self.player.getLogin()
        uid = int(self.player.getId())

        if not self.game.gameName is None:
            if self.game.gameName.startswith('#'):
                self.sendToRelay("P2PReconnect", [])

        self.send_CreateLobby(rankedMode, port, login, uid, 1)

        if self.game:
            self.game.addPlayer(self.player)
            self.game.specialInit(self.player)

            self.initDone = True

    def _send_host_game(self, mapname):
        ''' Create a lobby with a specific map'''
        self.game.hostPlayerFull = self.player
        self.game.setGameMap(mapname.lower())
        self.sendToRelay("HostGame", [mapname])

    def ConnectThroughProxy(self, peer, recurse=True):
        try:
            self.game.proxy.addCouple(self.player.login, peer.player.login)
            numProxy = self.game.proxy.findProxy(self.player.login, peer.player.login)

            if numProxy is not None:
                self.sendToRelay("DisconnectFromPeer", int(peer.player.id))
                self.send_ConnectToProxy(numProxy, peer.player.getIp(), str(peer.player.login), int(peer.player.id))

                if self.game:
                    self.game._logger.debug("%s is connecting through proxy to %s on port %i" % (
                        self.player.login, peer.player.login, numProxy))

                if peer.player.login not in self.proxyConnection:
                    self.proxyConnection.append(peer.player.login)

                if recurse:
                    peer.ConnectThroughProxy(self, False)
            else:
                self.log.debug(self.logGame + "Maximum proxies used")
        except:
            self.log.exception(self.logGame + "Something awful happened in a connect proxy thread!")


    def sendMessage(self, m):
        self.lobby.sendJSON(dict(command="notice", style="scores", text=str(m)))

    def sendGameInfo(self, skipDuration=False):
        try:
            self.games.mark_dirty(self.game.uuid)
        except:
            self.log.exception("Something awful happened in a sendinfo thread!")

    def registerScore(self, gameResult):
        try:
            gameId = self.game.uuid
            query = QSqlQuery(self.parent.db)
            for player in gameResult:

                score = gameResult[player]
                uid = -1
                if self.game.isAI(player):
                    nameAI = player.rstrip(string.digits)

                    query.prepare("SELECT id FROM AI_names WHERE login = ?")
                    query.addBindValue(nameAI)
                    query.exec_()
                    if query.size() > 0:
                        query.first()
                        uid = int(query.value(0))

                else:
                    query.prepare("SELECT id FROM login WHERE login = ?")
                    query.addBindValue(player)
                    query.exec_()
                    if query.size() > 0:
                        query.first()
                        uid = int(query.value(0))

                if uid != -1:
                    query.prepare("UPDATE game_player_stats set `score` = ? where `gameId` = ? AND `playerId` = ?")
                    query.addBindValue(score)
                    query.addBindValue(gameId)
                    query.addBindValue(uid)
                    query.exec_()


        except:
            self.log.exception("Something awful happened in a game  thread (registerScore) !")
            ##self.log.debug(self.logGame + "register scores done")


    def addAi(self, name, place, team):
        inGameName = name + str(place)

        self.game.addAI(inGameName)

        query = QSqlQuery(self.parent.db)
        # if the AI in the table ?
        queryStr = "INSERT INTO AI_names (login) VALUES ('%s')" % name
        query.exec_(queryStr)

        # get his rating
        queryStr = "SELECT mean, deviation FROM AI_rating WHERE id = (SELECT id FROM AI_names WHERE login = '%s')" % (
            name)
        query.exec_(queryStr)
        if query.size() != 1:

            # we dont have a mean yet, set default values
            trueSkill = faPlayer(Player(inGameName), Rating(1500, 500))
            queryStr = (
                           "INSERT INTO AI_rating (id, mean, deviation) values ((SELECT id FROM AI_names WHERE AI_names.login = '%s'),1500,500)") % (
                           name)
            query.exec_(queryStr)
        else:
            query.first()
            mean = query.value(0)
            dev = query.value(1)
            trueSkill = faPlayer(Player(inGameName), Rating(mean, dev))
        self.game.addTrueSkillPlayer(trueSkill)
        self.game.placePlayer(inGameName, place)
        self.game.assignPlayerToTeam(inGameName, team)


    def parsePlayerOption(self, value):
        options = value.split(' ')
        length = len(options)
        atype = options[0]
        name = " ".join(options[1:length - 2])
        name = name.encode('utf-8')
        place = int(options[length - 2])
        value = int(options[length - 1])
        return atype, name, place, value

    def registerTime(self, player):
        if self.game.isAI(player):
            table = "AI_names"
            player_name = player.rstrip(string.digits)
        else:
            table = "login"
            player_name = player

        query = QSqlQuery(self.parent.db)
        query.prepare("UPDATE game_player_stats set `scoreTime` = NOW() where `gameId` = ? AND `playerId` = (SELECT id FROM %s WHERE login = ?)" % table)
        query.addBindValue(self.game.uuid)
        query.addBindValue(player_name)
        query.exec_()
        query.finish()

    def fillGameStats(self):
        mapId = 0
        modId = 0

        # What the actual fucking fuck?
        if "thermo" in self.game.mapName.lower():
            self.game.setInvalid("This map is not ranked.")

        query = QSqlQuery(self.parent.db)
        # Everyone loves table sacns!
        queryStr = ("SELECT id FROM table_map WHERE filename LIKE '%/" + self.game.mapName + ".%'")
        query.exec_(queryStr)
        if query.size() > 0:
            query.first()
            mapId = query.value(0)

        if mapId != 0:
            query.prepare("SELECT * FROM table_map_unranked WHERE id = ?")
            query.addBindValue(mapId)
            query.exec_()
            if query.size() > 0:
                self.game.setInvalid("This map is not ranked.")

        # Why can't this be rephrased to use equality?
        queryStr = ("SELECT id FROM game_featuredMods WHERE gamemod LIKE '%s'" % self.game.getGamemod() )
        query.exec_(queryStr)

        if query.size() == 1:
            query.first()
            modId = query.value(0)
        query = QSqlQuery(self.parent.db)
        query.prepare(
            "UPDATE game_stats set `startTime` = NOW(), gameType = ?, gameMod = ?, mapId = ?, gameName = ? WHERE id = ?")
        query.addBindValue(str(self.game.gameType))
        query.addBindValue(modId)
        query.addBindValue(mapId)
        query.addBindValue(self.game.gameName)
        query.addBindValue(self.game.uuid)
        if not query.exec_():
            self.log.debug("fillGameStats error: ")
            self.log.debug(query.lastError())
            self.log.debug(self.game.mapName.lower())

        queryStr = ("UPDATE table_map_features set times_played = (times_played +1) WHERE map_id LIKE " + str(mapId))
        query.exec_(queryStr)

    def isModRanked(self, uidmod):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT ranked FROM table_mod WHERE uid LIKE ?")
        query.addBindValue(uidmod)

        if not query.exec_():
            self.log.debug("error isModRanked: ")
            self.log.debug(query.lastError())

        if query.size() != 0:
            query.first()
            if query.value(0) == 1:
                return True
        return False


    def fillAIStats(self, AIs):
        if len(AIs) == 0:
            return
        queryStr = ""

        for AI in AIs:
            place = self.game.getPositionOfPlayer(AI)
            color = self.game.getPlayerColor(place)
            faction = self.game.getPlayerFaction(place)
            team = self.game.getTeamOfPlayer(AI)

            rating = None

            for playerTS in self.game.trueSkillPlayers:
                if str(playerTS.getPlayer()) == str(AI):
                    rating = playerTS.getRating()
                    break

            mean = rating.getMean()
            dev = rating.getStandardDeviation()
            nameAI = str(AI).rstrip(string.digits)
            queryStr += (
                            "INSERT INTO `game_player_stats`(`AI`, `gameId`, `playerId`, `faction`, `color`, `team`, `place`, `mean`, `deviation`) VALUES (1, %s, (SELECT id FROM AI_names WHERE login = '%s'), %s, %s, %s, %i, %f, %f);") % (
                            str(self.game.uuid), nameAI, faction, color, team, place, mean, dev )

        query = QSqlQuery(self.parent.db)
        query.exec_(queryStr)

    def fillPlayerStats(self, players):
        queryStr = ""
        mean = 0.0
        dev = 0.0

        for player in players:

            name = player.getLogin()

            team = self.game.getTeamOfPlayer(name)

            if team != -1:

                place = int(self.game.getPositionOfPlayer(name))
                color = self.game.getPlayerColor(place)
                faction = self.game.getPlayerFaction(place)
                if color is None or faction is None:
                    self.log.error("wrong faction or color for place " + str(place) + " of player " + name)

                rating = None

                for playerTS in self.game.trueSkillPlayers:
                    if str(playerTS.getPlayer()) == str(name):
                        rating = playerTS.getRating()
                        break

                if rating is not None:
                    mean = rating.getMean()
                    dev = rating.getStandardDeviation()

                queryStr += (
                                "INSERT INTO `game_player_stats`(`gameId`, `playerId`, `faction`, `color`, `team`, `place`, `mean`, `deviation`) VALUES (%s, %s, %s, %s, %s, %i, %f, %f);") % (
                                str(self.game.uuid), str(player.id), faction, color, team, place, mean, dev)

        if queryStr != "":
            query = QSqlQuery(self.parent.db)
            if not query.exec_(queryStr):
                self.log.error("player staterror")
                self.log.error(query.lastError())
                self.log.error(queryStr)
        else:
            self.log.error(self.logGame + "No player stat :(")

    def disconnection(self):
        try:
            if self.player:
                self.player.gameThread = None

                if self.game:
                    if hasattr(self.game, "proxy"):
                        if self.game.proxy.removePlayer(self.player.getLogin()):
                            self.parent.parent.udpSocket.writeDatagram(
                                json.dumps(dict(command="cleanup", sourceip=self.player.getIp())), proxyServer, 12000)
                if self.connectivity_state.result() == Connectivity.PROXY:
                    wiki_link = "{}index.php?title=Connection_issues_and_solutions".format(Config['global']['wiki_url'])
                    text = "Your network is not setup right.<br>The server had to make you connect to other players by proxy.<br>Please visit <a href='{}'>{}</a>" + \
                           "to fix this.<br><br>The proxy server costs us a lot of bandwidth. It's free to use, but if you are using it often,<br>it would be nice to donate for the server maintenance costs,".format(wiki_link, wiki_link)

                    self.lobby.sendJSON(dict(command="notice", style="info", text=str(text)))
                self.player.game = None
        except:
            pass
        finally:
            self.abort()

    def on_socket_state_change(self, socketState):
        self.log.debug("State changed to {}".format(socketState))

    def on_error(self, socketError):
        if socketError == QtNetwork.QAbstractSocket.RemoteHostClosedError:
            self.log.debug("RemoteHostClosedError")
        elif socketError == QtNetwork.QAbstractSocket.HostNotFoundError:
            self.log.debug("HostNotFoundError")
        elif socketError == QtNetwork.QAbstractSocket.ConnectionRefusedError:
            self.log.debug("ConnectionRefusedError")
        else:
            self.log.debug("The following error occurred: %s." % self._socket.errorString())
        self.abort()

    def connectivity_state(self):
        return self._connectivity_state

    def address_and_port(self):
        return "{}:{}".format(self.player.getIp(), self.player.gamePort)

    def send_gpgnet_message(self, command_id, arguments):
        self.sendToRelay(command_id, arguments)

    @property
    def player(self):
        return self._player

    @player.setter
    def player(self, val):
        self._player = val

    def __str__(self):
        return "GameConnection(Player({}),Game({}))".format(self.player.id, self.game)

