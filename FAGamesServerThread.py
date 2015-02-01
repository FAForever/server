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

import string
import time
import json
import logging

from PySide.QtCore import QTimer, QObject
from PySide import QtCore, QtNetwork
from PySide.QtSql import *

from trueSkill.faPlayer import *
from trueSkill.Team import *
from trueSkill.Player import *
from faPackets import Packet
from config import config

logger = logging.getLogger(__name__)

from proxy import proxy

from functools import wraps

proxyServer = QtNetwork.QHostAddress("127.0.0.1")


def timed(f):
    @wraps(f)
    def wrapper(*args, **kwds):
        start = time.time()
        result = f(*args, **kwds)
        elapsed = (time.time() - start) * 1000
        if elapsed > 20:
            logger.info("%s took %s ms to finish" % (f.__name__, str(elapsed)))
        return result

    return wrapper


class FAGameThread(QObject):
    """
    FA game server thread spawned upon every incoming connection to
    prevent collisions.
    """

    def __init__(self, socket, parent=None):
        super(FAGameThread, self).__init__(parent)
        self.log = logging.getLogger(__name__)

        self.log.debug("Incoming game socket started")
        self.initTime = time.time()

        self.initDone = False

        self.udpToServer = 0

        self.connectedTo = []

        self.forcedConnections = {}
        self.sentConnect = {}

        self.forcedJoin = None
        self.proxies = {}
        self.proxyNotThrough = True

        self.noSocket = False
        self.player = None
        self.parent = parent
        self.logGame = "\t"
        self.tasks = None
        self.game = None

        self.packetCount = 0

        self.proxyConnection = []
        self.socket = socket
        self.socket.setSocketOption(QtNetwork.QTcpSocket.KeepAliveOption, 1)
        self.socket.disconnected.connect(self.disconnection)
        self.socket.error.connect(self.displayError)
        self.socket.stateChanged.connect(self.stateChange)

        if self.socket.state() == 3 and self.socket.isValid():

            self.crappyPorts = {}
            self.lastUdpPacket = {}
            self.udpTimeout = 0
            self.missedUdpFrom = {}
            self.triedToConnect = []
            self.dontSetMorePortPlease = False
            self.JoinGameDone = False

            # PINGING
            self.initPing = True
            self.ponged = False
            self.missedPing = 0
            self.pingTimer = QTimer(self)
            self.pingTimer.timeout.connect(self.ping)

            self.headerSizeRead = False
            self.headerRead = False
            self.chunkSizeRead = False
            self.fieldTypeRead = False
            self.fieldSizeRead = False
            self.blockSize = 0
            self.fieldSize = 0
            self.chunkSize = 0
            self.fieldType = 0
            self.chunks = []

            self.socket.readyRead.connect(self.readData)

            self.testUdp = False

            self.delaySkipped = False

            if not self.parent.db.isOpen():
                self.parent.db.open()

            self.canConnectToHost = False

            self.lastUpdate = None

            self.gamePort = 6112
            self.player = None

            self.infoDelayed = False
            self.connected = 1

            self.data = ''
            self.addData = False
            self.addedData = 0
            self.tryingconnect = 0

            self.lobby = None

            ip = 0

            if not self.noSocket:
                ip = self.socket.peerAddress().toString()
                # the player is not known, we search for him.
            self.player = self.parent.listUsers.findByIp(ip)
            if self.player is not None and self.noSocket == False:
                self.player.gameThread = self
                # reset the udpPacket from server state

                self.player.setReceivedUdp(False)
                self.player.setPort = False
                self.player.connectedToHost = False

                self.player.resetUdpPacket()
                self.gamePort = int(self.player.getGamePort())

                self.lobby = self.player.getLobbyThread()

                strlog = ("%s\t" % str(self.player.getLogin()))
                self.logGame = strlog

                for player in self.parent.listUsers.getAllPlayers():
                    if player is not None:
                        if player.getLogin() == self.player.getLogin():

                            # we check if there is already a connection socket to a game.
                            oldsocket = player.getGameSocket()
                            if oldsocket is not None:
                                if socket.state() == 3 and socket.isValid():
                                    socket.abort()
                                    player.setGameSocket(0)
                                    # We set the curremt game Socket.
                self.player.setGameSocket(self.socket)
                self.player.setWantGame(False)

            else:
                self.log.warning("No player found for this IP : " + str(self.socket.peerAddress().toString()))
                self.socket.abort()
                return

            if not self.noSocket:
                self.tasks = QTimer(self)
                self.tasks.timeout.connect(self.doTask)
                self.tasks.start(200)


        else:
            self.socket.abort()

    def containsAny(self, str, set):
        """Check whether 'str' contains ANY of the chars in 'set'"""
        return 1 in [c in str for c in set]

    def sendToRelay(self, action, commands):
        ''' send a command to the relay server. The relay server is inside the FAF lobby. It process & relay these messages to FA itself.'''
        message = {"key": action, "commands": commands}

        block = QtCore.QByteArray()
        out = QtCore.QDataStream(block, QtCore.QIODevice.ReadWrite)
        out.setVersion(QtCore.QDataStream.Qt_4_2)

        out.writeUInt32(0)
        out.writeQString(json.dumps(message))

        out.device().seek(0)
        out.writeUInt32(block.size() - 4)
        self.bytesToSend = block.size() - 4

        if hasattr(self, "socket"):
            try:
                if self.socket:
                    if self.socket.isValid() and self.socket.state() == 3:
                        if self.socket.write(block) == -1:
                            self.socket.abort()

                    else:
                        self.socket.abort()
                else:
                    self.socket.abort()
            except:
                if self.tasks is not None:
                    self.tasks.stop()
                self.pingTimer.stop()


    def readData(self):
        ''' Our standard protocol. The FA protocol is now decoded by the lobby itself. Easier to handle that way.'''
        if self.socket.isValid():
            if self.socket.bytesAvailable() == 0:
                return
            ins = QtCore.QDataStream(self.socket)
            ins.setVersion(QtCore.QDataStream.Qt_4_2)
            while not ins.atEnd():
                if self.noSocket == False and self.socket.isValid():
                    if self.blockSize == 0:
                        if self.noSocket == False and self.socket.isValid():
                            if self.socket.bytesAvailable() < 4:
                                return
                            self.blockSize = ins.readUInt32()
                        else:
                            return

                    if self.noSocket == False and self.socket.isValid():
                        if self.socket.bytesAvailable() < self.blockSize:
                            return

                    else:
                        return
                    action = ins.readQString()

                    self.handleAction2(action)

                    self.blockSize = 0

                else:
                    return

            return

    @timed
    def doTask(self):
        ''' Do task run regularly to check if some stuff needs to happen when players are inside the FA lobby.'''
        now = time.time()
        if now - self.initTime > 60 * 60:
            self.socket.abort()
            self.tasks.stop()
            return

        if self.forcedJoin:
            if now - self.forcedJoin > 5:
                self.game.log.debug("%s going to join through proxy" % (self.player.getLogin()))
                self.joinThroughProxy()

        forceConnection = []
        for forcedPlayer in self.forcedConnections:
            if now - self.forcedConnections[forcedPlayer] > 10:
                forceConnection.append(forcedPlayer)

        action = self.player.getAction()
        for forcedPlayer in forceConnection:
            if action != "HOST":
                self.connectThroughProxy(forcedPlayer)
                if self.game:
                    self.game.log.debug(
                        "%s must connect through proxy to %s " % (forcedPlayer.getLogin(), self.player.getLogin()))

        sentConnect = []
        for sentPlayer in self.sentConnect:
            if now - self.sentConnect[sentPlayer] > 15:
                sentConnect.append(sentPlayer)

        for sentPlayer in sentConnect:
            del self.sentConnect[sentPlayer]
            if action != "HOST":
                self.connectThroughProxy(sentPlayer)
                if self.game:
                    self.game.log.debug(
                        "%s must connect through proxy to %s (not connected after 10 sec of ConnectToPeer) " % (
                            sentPlayer.getLogin(), self.player.getLogin()))

        if self.noSocket or self.player is None or self.game is None:
            if self in self.parent.recorders:
                if self.tasks is not None:
                    self.tasks.stop()
            return

        state = self.game.getLobbyState()
        if state != "playing":
            # first we stop the timer
            self.tasks.stop()

            if self.player.setPort is False and now - self.initTime > 3:
                # after 3 seconds we still have nothing, we force it.
                self.player.setPort = True

            if self.player.setPort is False \
                    and self.dontSetMorePortPlease is False \
                    and self.initDone is True and self.packetCount <= 10:
                self.sendPacketForNAT()
                self.tasks.start(200)

            getUdp = self.player.getReceivedUdp()

            if getUdp == True and self.testUdp == False:
                # we must now test both socket

                address = QtNetwork.QHostAddress(str(self.player.getIp()))
                if self.player.getGamePort() != self.player.getUdpPacketPort():
                    self.parent.parent.udpSocket.writeDatagram(
                        "\x08PACKET_RECEIVED %i" % self.player.getGamePort(), address,
                        self.player.getGamePort())
                    self.parent.parent.udpSocket.writeDatagram(
                        "\x08PACKET_RECEIVED %i" % self.player.getUdpPacketPort(), address,
                        self.player.getUdpPacketPort())
                else:
                    self.parent.parent.udpSocket.writeDatagram(
                        "\x08PACKET_RECEIVED %i" % self.player.getGamePort(), address,
                        self.player.getGamePort())

                self.testUdp = True

            if action == "HOST":

                for playerInGame in self.game.getPlayers():
                    if str(playerInGame.game) != str(self.game.getuuid()):
                        # self.log.debug(self.logGame + "ERROR : This player is not in the game : " + playerInGame.getLogin())
                        self.game.addToDisconnect(playerInGame)
                        self.game.removePlayer(playerInGame)
                        self.game.removeFromAllPlayersToConnect(playerInGame)
                        self.game.removeTrueSkillPlayer(playerInGame)

                self.player.connectedToHost = True
                if self.player.setPort:
                    self.game.setGameHostPort(self.player.getGamePort())
                    self.game.receiveUdpHost = True

            if self.canConnectToHost and self.player.setPort:

                if self.game.receiveUdpHost and not self.player.connectedToHost:
                    self.connectToHost()

            if self.player.setPort and self.player.isConnectedToHost():
                checkConnect = self.game.isConnectRequired(self.player)
                checkDisconnect = self.game.isDisconnectRequired(self.player)

                if checkConnect:
                    self.connectToPeers()

                if checkDisconnect:
                    self.disconnectToPeers()

            # and we restart it.
            self.tasks.start(200)

    def ping(self):
        ''' Ping the relay server to check if the player is still there.'''
        if hasattr(self, "socket"):
            if self.ponged is False:
                if self.missedPing > 2:
                    self.log.debug(
                        self.logGame + " Missed 2 ping - Removing user IP " + self.socket.peerAddress().toString())
                    if self.tasks is not None:
                        self.tasks.stop()
                    self.pingTimer.stop()
                    if self in self.parent.recorders:
                        self.socket.abort()
                else:
                    self.sendToRelay("ping", [])
                    self.missedPing += 1
            else:
                self.sendToRelay("ping", [])
                self.ponged = False
                self.missedPing = 0

    def idleState(self):
        ''' game is waiting for init
         we find in what game the player is
         if he is hosting, the lobby will be in "idle" state, and we add his IP '''

        action = self.player.getAction()
        if action == "HOST":
            self.game = self.parent.games.getGameByUuid(self.player.getGame())
            if self.game is not None and str(self.game.getuuid()) == str(self.player.getGame()):
                self.game.setLobbyState("Idle")
                self.game.setHostIP(self.player.getIp())
                self.game.setHostLocalIP(self.player.getLocalIp())
                self.game.proxy = proxy.proxy()
                strlog = (
                    "%s.%s.%s\t" % (str(self.player.getLogin()), str(self.game.getuuid()), str(self.game.getGamemod())))
                self.logGame = strlog
                initmode = self.game.getInitMode()
                self.initSupcom(initmode)
            else:
                # No game found. I don't know why we got a connection, but we don't want it.
                if self.noSocket is False:
                    self.socket.abort()
                    self.log.debug("HOST - Can't find game")
                    if self.player:
                        if self.player.getLobbyThread():
                            self.player.getLobbyThread().sendJSON(dict(command="notice", style="kill"))

        elif action == "JOIN":
            self.game = self.parent.games.getGameByUuid(self.player.getGame())

            if self.game is not None and str(self.game.getuuid()) == str(self.player.getGame()):
                if self.player.getLogin() in self.game.packetReceived:
                    self.packetReceived[self.player.getLogin()] = []

                for otherPlayer in self.game.getPlayers():
                    if self.player.getAddress() in otherPlayer.UDPPacket:
                        otherPlayer.UDPPacket[self.player.getAddress()] = 0
                strlog = (
                    "%s.%s.%s\t" % (str(self.player.getLogin()), str(self.game.getuuid()), str(self.game.getGamemod())))
                self.logGame = strlog

                initmode = 0
                initmode = self.game.getInitMode()

                self.initSupcom(initmode)
            else:
                # game not found, so still initialize FA to avoid "black screen" errors reports in the forum.
                self.initSupcom(0)
                if self.noSocket is False:
                    self.socket.abort()
                    self.log.debug("JOIN - Can't find game")
                    # But we tell the lobby that FA must be killed.
                    self.lobby.sendJSON(dict(command="notice", style="kill"))

        else:
            # We tell the lobby that FA must be killed.
            self.lobby.sendJSON(dict(command="notice", style="kill"))
            self.log.debug("QUIT - No player action :(")

    def lobbyState(self):
        """
        Player is in lobby state. We need to tell him to connect to the host,
        or create the lobby itself if he is the host.
        """
        playeraction = self.player.getAction()
        if playeraction == "HOST":
            map = self.game.getMapName()
            self.createLobby(str(map))
        # if the player is joining, we connect him to host.
        elif playeraction == "JOIN":
            plist = []
            for player in self.game.getPlayers():
                plist.append(player.getLogin())

            self.game.addToConnect(self.player)
            self.canConnectToHost = True

    def handleAction2(self, action):
        """
        This code is starting to get messy...
        This function was created when the FA protocol was moved to the lobby itself
        """
        message = json.loads(action)
        self.handleAction(message["action"], message["chuncks"])


    def handleAction(self, key, values):
        """
        Handle GpgNetSend messages, wrapped in the JSON protocol
        :param key: command type
        :param values: command parameters
        :return: None
        """
        try:
            if key == 'ping':
                return

            elif key == 'Disconnected':
                return

            elif key == 'pong':
                self.ponged = True
                return

            elif key == 'Connected':
                uid = int(values[0])
                self.handleConnected(uid)

            elif key == 'connectedToHost':
                # player is connect to the host!
                self.player.connectedToHost = True

            elif key == 'Score':
                pass

            elif key == 'Bottleneck':
                pass

            elif key == 'BottleneckCleared':
                pass

            elif key == 'Desync':
                self.game.addDesync()

            elif key == 'ProcessNatPacket':
                self.handleNatPacket(values)

            elif key == 'GameState':
                state = values[0]
                self.handleGameState(state)

            elif key == 'GameOption':

                if values[0] in self.game.gameOptions:
                    self.game.gameOptions[values[0]] = values[1]

                if values[0] == "Slots":
                    self.game.maxPlayer = values[1]

                if values[0] == 'ScenarioFile':
                    raw = "%r" % values[1]
                    path = raw.replace('\\', '/')
                    map = str(path.split('/')[2]).lower()
                    curMap = ''
                    curMap = self.game.getGameMap()
                    if curMap != map:
                        self.game.setGameMap(map)
                        self.sendGameInfo()

                elif values[0] == 'Victory':
                    self.game.setGameType(values[1])

            elif key == 'GameMods':
                # find infos about mods...
                if values[0] == "activated":
                    if values[1] == 0:
                        self.game.mods = {}

                if values[0] == "uids":
                    self.game.mods = {}
                    query = QSqlQuery(self.parent.db)
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
                action = self.player.getAction()
                if action == "HOST":
                    for i, value in enumerate(values):
                        atype, name, place, resultvalue = self.parsePlayerOption(value)
                        if not ":" in name:
                            self.game.placePlayer(name, place)
                        if atype == "faction":
                            self.game.setPlayerFaction(place, resultvalue)
                        elif atype == "color":
                            self.game.setPlayerColor(place, resultvalue)
                        elif atype == "team":
                            team = resultvalue - 1
                            if ":" in name:
                                self.addAi(name, place, team)
                            else:
                                self.game.assignPlayerToTeam(name, team)
                        self.sendGameInfo()

            elif key == 'GameResult':
                ''' Preparing the data for recording the game result'''
                playerResult = self.game.getPlayerAtPosition(int(values[0]))
                if playerResult is not None:
                    result = values[1]
                    faresult = None
                    score = 0
                    if result.startswith("autorecall") or result.startswith("recall") or result.startswith(
                            "defeat") or result.startswith("victory") or result.startswith(
                            "score") or result.startswith("draw"):
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
                # stats never worked that well...
                pass

            elif key == 'Chat':
                # We should log that....
                pass

            elif key == 'OperationComplete':
                # This is for coop!
                self.log.debug(self.logGame + "OperationComplete: " + str(values))
                self.log.debug(self.logGame + "OperationComplete: " + str(values[1]))
                if self.game.isValid():
                    mission = -1
                    if int(values[0]) == 1:
                        self.log.debug(self.logGame + "Operation really Complete!")
                        query = QSqlQuery(self.parent.db)
                        query.prepare(
                            "SELECT id FROM coop_map WHERE filename LIKE '%/" + self.game.getGameMap() + ".%'")
                        query.exec_()
                        if query.size() > 0:
                            query.first()
                            mission = int(query.value(0))
                        else:
                            self.log.debug(self.logGame + "can't find coop map " + str(self.game.getGameMap()))
                    if mission != -1:

                        query.prepare(
                            "INSERT INTO `coop_leaderboard`(`mission`, `gameuid`, `secondary`, `time`) VALUES (?,?,?,?);")
                        query.addBindValue(mission)
                        query.addBindValue(self.game.getuuid())
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
                    query = QSqlQuery(self.parent.db)
                    query.prepare(
                        "DELETE FROM `galacticwar`.`reinforcements_groups` WHERE `userId` = (SELECT id FROM `faf_lobby`.`login` WHERE login.login = ?) AND `group` = ?")
                    query.addBindValue(playerResult)
                    query.addBindValue(group)
                    if query.exec_():
                        self.game.deleteGroup(group, playerResult)

            else:
                self.log.error(self.logGame + "Unknown key")
                self.log.error(self.logGame + key)
        except:
            self.log.exception(self.logGame + "Something awful happened in a game thread!")

    def handleConnected(self, uid):
        """
        Player established connection to peer
        :param uid: peer identifier
        :return: None
        """
        for player in self.parent.listUsers.players:
            playerUid = player.getId()

            if playerUid == uid:
                if self.game:
                    self.game.log.debug("%s Connected to : %s" % (player.getLogin(), self.player.getLogin()))

                if playerUid == self.game.getHostId():
                    self.forcedJoin = None

                if player in self.forcedConnections:
                    if self.game:
                        self.game.log.debug(
                            "Removed %s from forced connection of %s" % (player.getLogin(), self.player.getLogin()))
                    del self.forcedConnections[player]

                if player in self.sentConnect:
                    if self.game:
                        self.game.log.debug(
                            "Removed %s from sent connection of %s" % (player.getLogin(), self.player.getLogin()))
                    del self.sentConnect[player]

    def handleNatPacket(self, values):
        """
        NatPackets are used for establishing connections between players that are behind NAT,
        aka. hole-punching.
        :param values List containing packet contents directly
        """
        state = self.game.getLobbyState()
        if state != "playing":
            if "PACKET_RECEIVED" in values[1]:

                if not self.dontSetMorePortPlease:
                    splits = values[1].split(" ")
                    port = int(splits[len(splits) - 1])

                    if self.player.getLocalGamePort() == port and self.packetCount >= 4:
                        self.dontSetMorePortPlease = True

                    elif self.packetCount < 2:
                        self.sendPacketForNAT()
                        return

                    self.player.setGamePort(port)
                    self.setPort = True

                    self.player.setPort = True
                    json = {"debug": ("port used : %i" % port)}

                    for otherPlayer in self.game.getPlayers():
                        if self.player.getAddress() in otherPlayer.UDPPacket:
                            otherPlayer.UDPPacket[self.player.getAddress()] = 0

                    self.lobby.sendJSON(json)

                    if self.player.getAction() == "HOST":
                        self.game.setGameHostPort(port)

            elif "PLAYERID" in values[1]:
                playerName = " ".join(values[1].split()[2:])
                if hasattr(self.game, "getLoginName"):
                    playerName = self.game.getLoginName(playerName)

                thatPlayer = self.parent.listUsers.findByName(playerName)
                if thatPlayer != 0:
                    hisAdress = thatPlayer.getAddress()

                    addressIp = values[0].split(":")[0]

                    address = QtNetwork.QHostAddress(addressIp)
                    if address.protocol() == 0:

                        self.crappyPorts[playerName] = values[0]
                    else:
                        self.log.debug(self.logGame + "bad network address")

                self.game.receivedPacket(playerName, self.player.getLogin())


            elif "ASKREPLY" in values[1]:

                playerName = " ".join(values[1].split()[1:])

                if hasattr(self.game, "getLoginName"):
                    playerName = self.game.getLoginName(playerName)

                thatPlayer = self.parent.listUsers.findByName(playerName)
                if thatPlayer != 0:
                    hisAdress = thatPlayer.getAddress()
                    if hisAdress != values[0]:
                        addressIp = values[0].split(":")[0]
                        address = QtNetwork.QHostAddress(addressIp)
                        if address.protocol() == 0:
                            self.crappyPorts[playerName] = values[0]
                        else:
                            self.log.debug(self.logGame + "bad network address")

                if self.game.hasReceivedPacketFrom(playerName,
                                                   self.player.getLogin()) and self.game.hasReceivedPacketFrom(
                        self.player.getLogin(), playerName):
                    # That player ask for a reply, but he already get our id, we ignore his request.
                    return

                now = time.time()

                if not str(values[0]) in self.lastUdpPacket:
                    self.lastUdpPacket[str(values[0])] = now
                else:
                    if now - self.lastUdpPacket[str(values[0])] < 1:
                        return

                self.lastUdpPacket[str(values[0])] = now

                playerUid = self.player.getId()
                playerName = self.player.getLogin()

                if hasattr(self.game, "getPlayerName"):
                    playerName = self.game.getPlayerName(self.player)

                datasUdp = "/PLAYERID " + str(playerUid) + " " + playerName

                self.sendToRelay("SendNatPacket", [str(values[0]), datasUdp])


    def handleGameState(self, state):
        """
        Changes in game state
        :param state: new state
        :return: None
        """
        if state == 'Idle':
            # FA has just connected to us
            self.idleState()

        elif state == 'Lobby':
            # waiting for command
            self.lobbyState()

        elif state == 'Launching':
            # game launch, the user is playing !
            action = self.player.getAction()
            if self.tasks:
                self.tasks.stop()
            if self.player.getAction() == "HOST":

                self.game.numPlayers = self.game.getNumPlayer()

                self.game.setLobbyState("playing")

                if hasattr(self.game, "noStats"):
                    if not self.game.noStats:
                        self.fillGameStats()
                else:
                    self.fillGameStats()

                self.game.fixPlayerPosition()
                result = self.game.recombineTeams()

                self.fillPlayerStats(self.game.getPlayers())
                self.fillAIStats(self.game.AIs)
                for player in self.game.getPlayers():
                    player.setAction("PLAYING")
                    player.resetUdpPacket()

                if not all((i.count()) == self.game.finalTeams[0].count() for i in self.game.finalTeams):
                    self.game.setInvalid("All Teams don't the same number of players.")

                if len(self.game.finalTeams) == (len(self.game.AIs) + self.game.getNumPlayer()):
                    if self.game.getNumPlayer() > 3:
                        self.game.ffa = True
                        # ffa doesn't count for that much in rating.
                        self.game.partial = 0.25

                self.game.setTime()

                self.sendGameInfo()

                if self.game.getGameType() != 0 and self.game.getGamemod() != "coop":
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
                                if not "scca_coop_e02" in self.game.getGameMap().lower():
                                    self.game.setInvalid("Sim mods are not ranked")

                            else:
                                self.game.setInvalid("Sim mods are not ranked")

                        query = QSqlQuery(self.parent.db)
                        query.prepare("UPDATE `table_mod` SET `played`= `played`+1  WHERE uid = ?")
                        query.addBindValue(uid)
                        query.exec_()

                for playerTS in self.game.getTrueSkillPlayers():
                    if playerTS.getRating().getMean() < -1000:
                        self.game.setInvalid("You are playing with a smurfer.")

    def doEnd(self):
        ''' bybye player :('''
        self.player.setGameSocket(None)
        try:
            if hasattr(self, "game"):
                if self.game is not None:
                    # check if the game was started
                    if self.game.getLobbyState() == "playing":
                        curplayers = self.game.getNumPlayer()
                        allScoreHere = False
                        if hasattr(self.game, "isAllScoresThere"):
                            allScoreHere = self.game.isAllScoresThere()

                        if curplayers == 0 or allScoreHere == True:
                            self.game.setLobbyState("closed")
                            self.sendGameInfo()

                            if hasattr(self.game, "noStats"):
                                if not self.game.noStats:
                                    query = QSqlQuery(self.parent.db)
                                    queryStr = (
                                        "UPDATE game_stats set `EndTime` = NOW() where `id` = " + str(
                                            self.game.getuuid()))
                                    query.exec_(queryStr)
                            else:
                                query = QSqlQuery(self.parent.db)
                                queryStr = (
                                    "UPDATE game_stats set `EndTime` = NOW() where `id` = " + str(self.game.getuuid()))
                                query.exec_(queryStr)

                            if self.game.getDesync() > 20:
                                self.game.setInvalid("Too many desyncs")

                            if hasattr(self.game, "noStats"):
                                if not self.game.noStats:
                                    self.registerScore(self.game.gameResult)
                            else:
                                self.registerScore(self.game.gameResult)

                            self.game.specialEnding(self.log, self.parent.db, self.parent.listUsers)

                            for playerTS in self.game.getTrueSkillPlayers():
                                name = playerTS.getPlayer()
                                for player in self.parent.listUsers.getAllPlayers():
                                    if player is not None:
                                        if str(name) == player.getLogin():
                                            for conn in self.parent.parent.FALobby.recorders:
                                                conn.sendJSON(self.parent.parent.jsonPlayer(player))

                            self.parent.games.removeGame(self.game)
                            self.game = None
        except:
            self.log.exception("Something awful happened in a game  thread (ending) !")

    def ejectPlayer(self, player):
        self.sendToRelay("EjectPlayer", [int(player.getId())])

    def initSupcom(self, rankedMode):
        ''' We init FA with the right infos about the player.'''
        port = None
        login = None
        uid = None
        if self.game is None:

            text = "You were unable to connect to the host because he has left the game."
            self.lobby.sendJSON(dict(command="notice", style="kill"))
            self.lobby.sendJSON(dict(command="notice", style="info", text=str(text)))
            self.socket.abort()
            if self.tasks:
                self.tasks.stop()
            if self.pingTimer:
                self.pingTimer.stop()
            return
        port = self.player.getGamePort()

        if hasattr(self.game, "getPlayerName"):
            login = self.game.getPlayerName(self.player)
        else:
            login = self.player.getLogin()

        uid = int(self.player.getId())
        if not self.game.getGameName() is None:
            if self.game.getGameName()[0] == '#':
                self.sendToRelay("P2PReconnect", [])

        self.sendToRelay("CreateLobby", [rankedMode, port, login, uid, 1])

        if self.game:
            self.game.addPlayer(self.player)
            self.game.specialInit(self.player)

        self.sendPacketForNAT()
        self.pingTimer.start(31000)
        self.initDone = True

    def sendPacketForNAT(self):
        ''' Send a nat packet to the server'''
        self.packetCount += 1
        datas = "/PLAYERID " + str(self.player.getId()) + " " + self.player.getLogin()

        # FIXME: we should make this a hostname and let the client resolve.
        self.sendToRelay("SendNatPacket", [config['global']['lobby_ip'] + ":30351", datas])

    def createLobby(self, mapname):
        ''' Create a lobby with a specific map'''
        self.game.hostPlayerFull = self.player
        self.game.setLobbyState("open")
        self.game.setGameMap(mapname.lower())
        self.sendToRelay("HostGame", [mapname])

    def connectToHost(self):
        '''We connect to host
        Address is the address of the host
        The others arguments are : Host Name and host Id'''
        if self.JoinGameDone is True:
            return
        gameAddress = ''
        hostId = ''
        localConnect = False

        if self.game.getHostIp() == self.player.getIp():
            localConnect = True
            gameAddress = self.game.getGameLocalAddress()
        else:
            gameAddress = self.game.getGameAddress()

        hostId = self.game.getHostId()

        connectToHostSent = False

        if not localConnect:

            if self.game.hasReceivedPacketFrom(self.player.getLogin(), self.game.getHostName()):
                if self.game.hasReceivedPacketFrom(self.game.getHostName(), self.player.getLogin()):
                    if self.game.getHostName() in self.crappyPorts:
                        gameAddress = self.crappyPorts[self.game.getHostName()]

                    self.JoinGameDone = True

                    if hasattr(self.game, "getHostNameForJoin"):
                        hostname = self.game.getHostNameForJoin()
                    else:
                        hostname = self.game.getHostName()

                    addressToConnect = gameAddress
                    if hasattr(self.game, "hostPlayerFull"):
                        try:
                            hostPlayer = self.game.hostPlayerFull
                            if hasattr(hostPlayer, "resolvedAddress"):
                                addressToConnect = "%s:%s" % (
                                    hostPlayer.resolvedAddress, str(gameAddress.split(":")[1]))
                        except:
                            addressToConnect = gameAddress

                    self.sendToRelay("JoinGame", [str(addressToConnect), str(hostname), int(hostId)])
                    self.player.UDPPacket[str(gameAddress)] = 0

                    connectToHostSent = True

            if not connectToHostSent:
                if self.game.getHostName() in self.crappyPorts:
                    gameAddress = self.crappyPorts[self.game.getHostName()]
                count = self.player.countUdpPacket(str(gameAddress))
                if count < 15:

                    playerName = self.player.getLogin()
                    if hasattr(self.game, "getPlayerName"):
                        playerName = self.game.getPlayerName(self.player)

                    datas = "/ASKREPLY " + playerName
                    self.sendToRelay("SendNatPacket", [str(gameAddress), datas])
                    self.player.addCountUdpPacket(str(gameAddress))

                else:
                    self.forceJoin()

        else:
            if self.noSocket == False and self.socket.isValid():
                if hasattr(self.game, "getHostNameForJoin"):
                    hostname = self.game.getHostNameForJoin()
                else:
                    hostname = self.game.getHostName()

                self.sendToRelay("JoinGame", [str(gameAddress), str(hostname), int(hostId)])

            self.player.connectedToHost = True


    def disconnectToPeers(self):

        '''Connect the player to others'''

        playerToDisconnects = []

        playerToDisconnects = self.game.getDisconnectList(self.player)

        for playerToDisconnect in playerToDisconnects:
            # we only need his uuid

            uuid = playerToDisconnect.getId()
            if playerToDisconnect in self.connectedTo:
                self.sendToRelay("DisconnectFromPeer", [int(uuid)])
                self.connectedTo.remove(playerToDisconnect)

            if playerToDisconnect in self.forcedConnections:
                del self.forcedConnections[playerToDisconnect]

            if playerToDisconnect in self.sentConnect:
                del self.sentConnect[playerToDisconnect]

            # Now, that player is disconnected. We can remove it to the list of disconnection for self
            self.game.removeFromDisconnect(self.player, playerToDisconnect)


    def connectToPeers(self):
        try:

            # for all the player in the connection list of current player.
            playerToConnects = []

            plist = []
            for player in self.game.getPlayers():
                plist.append(player.getLogin())

            playerToConnects = self.game.getConnectList(self.player)
            for playerToConnect in playerToConnects:
                self.log.debug(self.logGame + "trying to connect " + playerToConnect.getLogin() + " with " + str(
                    self.player.getLogin()))

                if playerToConnect.game is None or str(playerToConnect.game) != str(self.game.getuuid()):
                    self.log.debug(
                        self.logGame + "CONFIRM : trying to connect " + playerToConnect.getLogin() + " with " + str(
                            self.player.getLogin()))
                    self.log.debug(
                        self.logGame + "ERROR : This player is not in the game : " + playerToConnect.getLogin())
                    self.game.removeFromConnect(self.player, playerToConnect)
                    self.game.removePlayer(playerToConnect)
                    self.game.removeFromAllPlayersToConnect(playerToConnect)
                    self.game.removeTrueSkillPlayer(playerToConnect)
                    continue

                localConnect = False

                if playerToConnect.getReceivedUdp() == False or self.player.getReceivedUdp() == False or self.player.setPort == False or playerToConnect.setPort == False:
                    self.log.debug(self.logGame + "UDP Problem")
                    continue

                if self.game.getHostName() != self.player.getLogin():
                    if not playerToConnect.isConnectedToHost():
                        self.log.debug(self.logGame + "Not connected to host")
                        continue

                action = self.player.getAction()
                if action != "HOST":
                    if self.game.proxy.coupleExists(self.player.getLogin(), playerToConnect.getLogin()):
                        self.log.debug(
                            self.logGame + "Must connect to " + playerToConnect.getLogin() + " through proxy")
                        self.connectThroughProxy(playerToConnect)
                        if not playerToConnect in self.connectedTo:
                            self.connectedTo.append(playerToConnect)
                        self.game.removeFromConnect(self.player, playerToConnect)
                        continue

                address = ""
                # if both player got the same ip ...
                if self.player.getIp() == playerToConnect.getIp():
                    address = playerToConnect.getLocalAddress()
                    localConnect = True
                else:
                    address = playerToConnect.getAddress()

                # and his login name
                playerName = playerToConnect.getLogin()

                originalName = playerName
                if hasattr(self.game, "getPlayerName"):
                    playerName = self.game.getPlayerName(playerToConnect)
                # and his UUID
                uuid = playerToConnect.getId()

                # connection
                if not localConnect:
                    if self.game.hasReceivedPacketFrom(self.player.getLogin(), playerToConnect.getLogin()):

                        if self.game.hasReceivedPacketFrom(playerToConnect.getLogin(), self.player.getLogin()):
                            # both player has receive their packet, we can connect them !
                            if originalName in self.crappyPorts:
                                address = self.crappyPorts[originalName]

                            addressToConnect = address
                            if hasattr(playerToConnect, "resolvedAddress"):
                                try:
                                    addressToConnect = "%s:%s" % (
                                        playerToConnect.resolvedAddress, str(address.split(":")[1]))
                                    self.log.debug("address : " + addressToConnect)
                                except:
                                    addressToConnect = address
                            else:
                                addressToConnect = address
                            self.sendToRelay("ConnectToPeer", [str(addressToConnect), str(playerName), int(uuid)])
                            self.connectedTo.append(playerToConnect)
                            self.player.UDPPacket[str(address)] = 0
                            # Now, that player is connected. We can remove it to the list of connection for self
                            self.game.removeFromConnect(self.player, playerToConnect)
                            self.sentConnect[playerToConnect] = time.time()

                            ## let him breath for now
                            break

                        else:
                            count = self.player.countUdpPacket(str(address))
                            if count < 15:
                                if originalName in self.crappyPorts:
                                    address = self.crappyPorts[originalName]

                                # the player to connect has not receive our packet, we resend.

                                playerUid = self.player.getId()
                                playerName = self.player.getLogin()

                                if hasattr(self.game, "getPlayerName"):
                                    playerName = self.game.getPlayerName(self.player)

                                # send some info about us and ask for a reply.
                                datas = "/PLAYERID " + str(playerUid) + " " + playerName
                                reply = Packet(SendNatPacket=[str(address), datas])
                                if self.noSocket == False and self.socket.isValid():
                                    self.sendToRelay("SendNatPacket", [str(address), datas])

                                datas = "/ASKREPLY " + playerName
                                reply = Packet(SendNatPacket=[str(address), datas])
                                if self.noSocket == False and self.socket.isValid():
                                    self.sendToRelay("SendNatPacket", [str(address), datas])

                                self.player.addCountUdpPacket(str(address))
                            else:
                                if playerName in self.crappyPorts:
                                    address = self.crappyPorts[playerName]

                                self.forceConnect(playerToConnect)

                                self.connectedTo.append(playerToConnect)
                                self.player.UDPPacket[str(address)] = 0
                                self.game.removeFromConnect(self.player, playerToConnect)
                                break
                    else:
                        count = self.player.countUdpPacket(str(address))
                        if count < 15:
                            if originalName in self.crappyPorts:
                                address = self.crappyPorts[originalName]

                            playerUid = self.player.getId()
                            playerName = self.player.getLogin()

                            if hasattr(self.game, "getPlayerName"):
                                playerName = self.game.getPlayerName(self.player)


                            # the player to connect has not receive our packet, we resend.
                            datas = "/PLAYERID " + str(playerUid) + " " + playerName
                            if self.noSocket == False and self.socket.isValid():
                                self.sendToRelay("SendNatPacket", [str(address), datas])

                            datas = "/ASKREPLY " + playerName
                            if self.noSocket == False and self.socket.isValid():
                                self.sendToRelay("SendNatPacket", [str(address), datas])

                            self.player.addCountUdpPacket(str(address))
                        else:
                            if originalName in self.crappyPorts:
                                address = self.crappyPorts[originalName]

                            self.forceConnect(playerToConnect)

                            self.connectedTo.append(playerToConnect)
                            self.player.UDPPacket[str(address)] = 0
                            self.game.removeFromConnect(self.player, playerToConnect)
                            break
                            # connection to local
                else:
                    self.sendToRelay("ConnectToPeer", [str(address), str(playerName), int(uuid)])
                    self.connectedTo.append(playerToConnect)
                    self.game.removeFromConnect(self.player, playerToConnect)
                    break
        except:
            self.log.exception(self.logGame + "Something awful happened in a connect thread !")


    def forceJoin(self):
        try:
            self.game.log.debug("%s in forced join" % (self.player.getLogin()))
            self.JoinGameDone = True
            self.forcedJoin = time.time()
        except:
            self.log.exception(self.logGame + "Something awful happened in a join forced thread !")

    def joinThroughProxy(self):
        try:

            self.forcedJoin = None

            self.game.proxy.addCouple(self.player.getLogin(), self.game.getHostName())
            numProxy = self.game.proxy.findProxy(self.player.getLogin(), self.game.getHostName())

            if numProxy is not None:
                hostId = self.game.getHostId()
                hostname = self.game.getHostName()
                if hasattr(self.game, "getHostNameForJoin"):
                    hostname = self.game.getHostNameForJoin()

                self.sendToRelay("JoinProxy", [numProxy, self.game.getHostIp(), str(hostname), int(hostId)])
                self.game.log.debug("%s is joining through proxy to %s on port %i" % (
                    self.player.getLogin(), self.game.getHostName(), numProxy))
                if not self.game.getHostName() in self.proxyConnection:
                    self.proxyConnection.append(self.game.getHostName())

                # Host connect to this player through proxy

                host = self.parent.listUsers.findByName(self.game.getHostName())
                if host:
                    if host.gameThread:
                        host.gameThread.connectThroughProxy(self.player, sendToOther=False, init=True)
                        host.gameThread.connectedTo.append(self.player)
                        if self.game.getHostName() in self.game.connections:
                            self.game.removeFromConnect(host, self.player)
                    else:
                        text = "You were unable to connect to " + hostname + " because he has left the game."
                        self.lobby.sendJSON(dict(command="notice", style="kill"))
                        self.lobby.sendJSON(dict(command="notice", style="info", text=str(text)))
                        self.warningProxySent = True

                else:
                    text = "You were unable to connect to " + hostname + " because he has left the game."
                    self.lobby.sendJSON(dict(command="notice", style="kill"))
                    self.lobby.sendJSON(dict(command="notice", style="info", text=str(text)))
                    self.warningProxySent = True



            else:
                self.log.debug(self.logGame + "Maximum proxies used")
        except:
            self.log.exception(self.logGame + "Something awful happened in a join proxy thread !")


    def forceConnect(self, playerToConnect):
        # self.log.debug(self.logGame + "Forced connect to " + playerToConnect.getLogin())
        self.forcedConnections[playerToConnect] = time.time()
        if playerToConnect.getLogin() in self.crappyPorts:
            address = self.crappyPorts[playerToConnect.getLogin()]
        else:
            address = playerToConnect.getAddress()

        if hasattr(self.game, "getPlayerName"):
            playerName = self.game.getPlayerName(playerToConnect)
        else:
            playerName = playerToConnect.getLogin()

        uuid = playerToConnect.getId()

        self.sendToRelay("ConnectToPeer", [str(address), str(playerName), int(uuid)])
        self.connectedTo.append(playerToConnect)
        self.player.UDPPacket[str(address)] = 0

        if playerToConnect.getLogin() in self.game.connections:
            self.game.removeFromConnect(self.player, playerToConnect)

        self.game.log.debug(
            "Forcing connection between %s and %s " % (playerToConnect.getLogin(), self.player.getLogin()))


    def connectThroughProxy(self, playerToConnect, sendToOther=True, init=False):
        try:
            numProxy = None

            if playerToConnect in self.forcedConnections:
                del self.forcedConnections[playerToConnect]

            if playerToConnect in self.sentConnect:
                del self.sentConnect[playerToConnect]

            if playerToConnect.gameThread is None:
                return

            self.game.proxy.addCouple(self.player.getLogin(), playerToConnect.getLogin())
            numProxy = self.game.proxy.findProxy(self.player.getLogin(), playerToConnect.getLogin())

            if numProxy is not None:
                uuid = playerToConnect.getId()

                if hasattr(self.game, "getPlayerName"):
                    playerName = self.game.getPlayerName(playerToConnect)
                else:
                    playerName = playerToConnect.getLogin()

                self.sendToRelay("DisconnectFromPeer", int(uuid))
                self.sendToRelay("ConnectToProxy", [numProxy, playerToConnect.getIp(), str(playerName), int(uuid)])

                if self.game:
                    self.game.log.debug("%s is connecting through proxy to %s on port %i" % (
                        self.player.getLogin(), playerToConnect.getLogin(), numProxy))

                if not playerToConnect.getLogin() in self.proxyConnection:
                    self.proxyConnection.append(playerToConnect.getLogin())

                if sendToOther and self.player.getLogin() != self.game.getHostName():
                    playerToConnect.gameThread.connectThroughProxy(self.player, sendToOther=False)
                    if not self.player in playerToConnect.gameThread.connectedTo:
                        playerToConnect.gameThread.connectedTo.append(self.player)

                    if playerToConnect.getLogin() in self.game.connections:
                        self.game.removeFromConnect(playerToConnect, self.player)
            else:
                self.log.debug(self.logGame + "Maximum proxies used")
        except:
            self.log.exception(self.logGame + "Something awful happened in a connect proxy thread !")


    def sendMessage(self, m):
        self.lobby.sendJSON(dict(command="notice", style="scores", text=str(m)))

    def sendGameInfo(self, skipDuration=False):
        try:
            self.parent.addDirtyGame(self.game.getuuid())
        except:
            self.log.exception("Something awful happened in a sendinfo thread !")

    def registerScore(self, gameResult):
        try:
            gameId = self.game.getuuid()
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
        queryStr = "INSERT INTO AI_names (login) VALUES ('%s')" % (name)
        query.exec_(queryStr)

        # get his rating
        queryStr = ("SELECT mean, deviation FROM AI_rating WHERE id = (SELECT id FROM AI_names WHERE login = '%s')") % (
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
        query = QSqlQuery(self.parent.db)
        gameId = self.game.getuuid()
        if self.game.isAI(player):
            nameAI = player.rstrip(string.digits)
            queryStr = (
                           "UPDATE game_player_stats set `scoreTime` = NOW() where `gameId` = %s AND `playerId` = (SELECT id FROM AI_names WHERE login = '%s' )") % (
                           str(gameId), nameAI)
        else:
            queryStr = (
                           "UPDATE game_player_stats set `scoreTime` = NOW() where `gameId` = %s AND `playerId` = (SELECT id FROM login WHERE login = '%s' )") % (
                           str(gameId), player)
        query.exec_(queryStr)

    def fillGameStats(self):
        mapId = 0
        modId = 0
        if "thermo" in self.game.getGameMap().lower():
            self.game.setInvalid("This map is not ranked.")
        query = QSqlQuery(self.parent.db)
        queryStr = ("SELECT id FROM table_map WHERE filename LIKE '%/" + self.game.getGameMap() + ".%'")
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

        queryStr = ("SELECT id FROM game_featuredMods WHERE gamemod LIKE '%s'" % self.game.getGamemod() )
        query.exec_(queryStr)

        if query.size() == 1:
            query.first()
            modId = query.value(0)
        query = QSqlQuery(self.parent.db)
        query.prepare(
            "UPDATE game_stats set `startTime` = NOW(), gameType = ?, gameMod = ?, mapId = ?, gameName = ? WHERE id = ?")
        query.addBindValue(str(self.game.getGameType()))
        query.addBindValue(modId)
        query.addBindValue(mapId)
        query.addBindValue(self.game.getGameName())
        query.addBindValue(self.game.getuuid())
        if not query.exec_():
            self.log.debug("fillGameStats error: ")
            self.log.debug(query.lastError())
            self.log.debug(self.game.getGameMap().lower())

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
        mean = 0.0
        dev = 0.0

        for AI in AIs:
            place = self.game.getPositionOfPlayer(AI)
            color = self.game.getPlayerColor(place)
            faction = self.game.getPlayerFaction(place)
            team = self.game.getTeamOfPlayer(AI)

            rating = None

            for playerTS in self.game.getTrueSkillPlayers():
                if str(playerTS.getPlayer()) == str(AI):
                    rating = playerTS.getRating()
                    break

            mean = rating.getMean()
            dev = rating.getStandardDeviation()
            nameAI = str(AI).rstrip(string.digits)
            queryStr += (
                            "INSERT INTO `game_player_stats`(`AI`, `gameId`, `playerId`, `faction`, `color`, `team`, `place`, `mean`, `deviation`) VALUES (1, %s, (SELECT id FROM AI_names WHERE login = '%s'), %s, %s, %s, %i, %f, %f);") % (
                            str(self.game.getuuid()), nameAI, faction, color, team, place, mean, dev )

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

                for playerTS in self.game.getTrueSkillPlayers():
                    if str(playerTS.getPlayer()) == str(name):
                        rating = playerTS.getRating()
                        break

                if rating is not None:
                    mean = rating.getMean()
                    dev = rating.getStandardDeviation()

                queryStr += (
                                "INSERT INTO `game_player_stats`(`gameId`, `playerId`, `faction`, `color`, `team`, `place`, `mean`, `deviation`) VALUES (%s, %s, %s, %s, %s, %i, %f, %f);") % (
                                str(self.game.getuuid()), str(player.getId()), faction, color, team, place, mean, dev )

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
                if len(self.proxyConnection) > 0:
                    players = ", ".join(self.proxyConnection)

                    text = "You had trouble connecting to some player(s) : <br>" + players + ".<br><br>The server tried to make you connect through a proxy server, running on the FAF server.<br>It can be caused by a problem with that player, or a problem on your side.<br>If you see this message often, you probably have a connection problem. Please visit <a href='" + \
                           config['global']['www_url'] + "mediawiki/index.php?title=Connection_issues_and_solutions'>" + \
                           config['global'][
                               'www_url'] + "mediawiki/index.php?title=Connection_issues_and_solutions</a> to fix this.<br><br>The proxy server costs us a lot of bandwidth. It's free to use, but if you are using it often,<br>it would be nice to donate for the server maintenance costs, at your discretion."

                    self.lobby.sendJSON(dict(command="notice", style="info", text=str(text)))
                self.player.setGameSocket(None)
                self.player.game = None
            self.done()
        except:
            pass

    def done(self):
        self.noSocket = True
        if self in self.parent.recorders:
            if self.tasks is not None:
                self.tasks.stop()

        self.triedToConnect = []

        if self.game != 0 and self.game is not None:

            state = self.game.getLobbyState()

            # if game in lobby state
            if state != "playing":
                self.game.addToDisconnect(self.player)
                self.game.removePlayer(self.player)
                self.game.removeFromAllPlayersToConnect(self.player)
                self.game.removeTrueSkillPlayer(self.player)

                getAction = self.player.getAction()

                if getAction == "HOST":
                    # if the player was the host  (so, not playing), we remove his game

                    self.game.setLobbyState("closed")  #
                    self.sendGameInfo()
                    self.parent.games.removeGame(self.game)
                    self.game = None

                elif getAction == 'JOIN':
                    # self.player.setAction("NOTHING")
                    minplayers = self.game.getMinPlayers()
                    curplayers = self.game.getNumPlayer()

                    if minplayers == 2 or curplayers == 0:
                        self.game.setLobbyState("closed")

                        self.sendGameInfo()
                        self.parent.games.removeGame(self.game)
                        self.game = None
            # if the game was in play.
            else:
                self.game.removePlayer(self.player)
                self.sendGameInfo()

            self.doEnd()

        # we remove the gameSocket and reset the udp packet state
        if self.player is not None:
            self.player.setReceivedUdp(False)
            self.player.setGameSocket(0)
            self.player.resetUdpFrom()

        # CLEANING
        self.player = None
        self.game = None
        self.lobby = None

        if self.socket is not None:
            try:
                self.socket.readyRead.disconnect(self.dataReception)
                self.socket.disconnected.disconnect(self.disconnection)
                self.socket.error.disconnect(self.displayError)
            except:
                pass
            self.socket.abort()
            self.socket.deleteLater()
        self.missedUdpFrom = {}
        self.triedToConnect = []

        if self in self.parent.recorders:
            self.parent.removeRecorder(self)

    def stateChange(self, socketState):
        if socketState != QtNetwork.QAbstractSocket.ClosingState:
            self.log.debug("socket about to close")
        elif socketState != QtNetwork.QAbstractSocket.UnconnectedState:
            self.log.debug("socket not connected")
        if socketState != QtNetwork.QAbstractSocket.ConnectedState:
            self.log.debug("not connected")
            self.socket.abort()

    def displayError(self, socketError):
        if socketError == QtNetwork.QAbstractSocket.RemoteHostClosedError:
            self.log.warning("RemoteHostClosedError")
        elif socketError == QtNetwork.QAbstractSocket.HostNotFoundError:
            self.log.warning("HostNotFoundError")
        elif socketError == QtNetwork.QAbstractSocket.ConnectionRefusedError:
            self.log.warning("ConnectionRefusedError")
        else:
            self.log.warning("The following error occurred: %s." % self.socket.errorString())
