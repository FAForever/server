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
from socket import socket
import time
import json
import logging
import functools

from PySide import QtNetwork
from PySide.QtSql import *

from server.abc.base_game import GameConnectionState
from server.connectivity import TestPeer, Connectivity
from server.games.game import Game, GameState, Victory
from server.decorators import with_logger, timed
from server.games_service import GamesService
from server.protocol.gpgnet import GpgNetServerProtocol
from server.subscribable import Subscribable


logger = logging.getLogger(__name__)


from server.protocol.protocol import QDataStreamProtocol

from config import Config

PROXY_SERVER = ('127.0.0.1', 12000)

@with_logger
class GameConnection(Subscribable, GpgNetServerProtocol, QDataStreamProtocol):
    """
    Responsible for the games protocol.
    """

    def __init__(self, loop, users, games: GamesService, db):
        Subscribable.__init__(self)
        QDataStreamProtocol.__init__(self)
        self._logger.info('GameConnection initializing')
        self._state = GameConnectionState.INITIALIZING
        self.loop = loop
        self.users = users
        self.games = games

        self.db = db
        self.log = logging.getLogger(__name__)
        self.initTime = time.time()
        self.proxies = {}
        self._player = None
        self.logGame = "\t"
        self._game = None
        self.proxyConnection = []

        self.last_pong = time.time()

        self.player = None
        self._socket = None
        self.lobby = None
        self._transport = None
        self.nat_packets = {}
        self.ping_task = None
        self._connectivity_state = None

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

    def on_connection_made(self, peer_name):
        """
        Accept a connected socket for this GameConnection

        Will look up the user using the provided users service,
        followed by obtaining the Game object that the user wishes to join.
        :raise AssertionError
        :return: bool
        """
        self._logger.debug("Accepting connection from {}".format(peer_name))

        self.lobby = None
        ip, port = peer_name
        self.player = self.users.findByIp(ip)
        self.log.debug("Resolved user to {} through lookup by {}:{}".format(self.player, ip, port))

        if self.player is None:
            self.log.info("Player not found for IP: %s " % ip)
            self.abort()
            return False

        if self.player.game is None:
            self.log.info("Player hasn't indicated that he wants to join a game")
            self.abort()
            return False

        self.game = self.player.game
        self.player.game_connection = self
        self.lobby = self.player.lobby_connection

        self.player.setPort = False
        self.player.connectedToHost = False


        strlog = ("%s\t" % str(self.player.getLogin()))
        self.logGame = strlog

        self.ping_task = asyncio.async(self.ping())
        self.player.wantToConnectToGame = False
        self._state = GameConnectionState.INITIALIZED
        return True

    def sendToRelay(self, action, commands):
        message = {"key": action, "commands": commands}
        self.send_message(json.dumps(message))

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
        assert self.game
        self.send_Ping()
        action = self.player.action

        if action == "HOST":
            self.game.state = GameState.LOBBY
            self._state = GameConnectionState.CONNECTED_TO_HOST
            self.game.add_game_connection(self)
            self.game.setHostIP(self.player.ip)
            strlog = (
                "%s.%s.%s\t" % (str(self.player.getLogin()), str(self.game.uuid), str(self.game.getGamemod())))
            self.logGame = strlog
            self._send_create_lobby()

        elif action == "JOIN":
            strlog = (
                "%s.%s.%s\t" % (str(self.player.getLogin()), str(self.game.uuid), str(self.game.getGamemod())))
            self.logGame = strlog
            self._send_create_lobby()

        else:
            self.log.debug("QUIT - No player action :(")
            self.abort()

    def abort(self):
        """
        Abort the connection, calling doEnd() first
        :return:
        """
        if self._state is GameConnectionState.ABORTED or self._state is GameConnectionState.ENDED:
            return
        self._state = GameConnectionState.ABORTED
        self.log.debug("{}.abort()".format(self))
        try:
            self.doEnd()
            if self.player.lobby_connection:
                self.player.lobby_connection.sendJSON(dict(command="notice", style="kill"))
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
                      self.player.id) as peer_test:
            self._connectivity_state = yield from peer_test.determine_connectivity()
            self.sendToRelay('ConnectivityState', [self.player.getId(),
                                                   self._connectivity_state.value])

        playeraction = self.player.action
        if playeraction == "HOST":
            map = self.game.mapName
            self.send_HostGame(map)
        # if the player is joining, we connect him to host.
        elif playeraction == "JOIN":
            yield from self.ConnectToHost(self.game.hostPlayer.game_connection)

    @timed(limit=0.1)
    def on_message_received(self, message):
        """
        This code is starting to get messy...
        This function was created when the FA protocol was moved to the lobby itself
        """
        try:
            message = json.loads(message)
            message["command_id"] = message['action']
            message["arguments"] = message['chuncks']
            self.notify(message)
            asyncio.async(self.handle_action(message["action"], message["chuncks"]))
        except ValueError as ex:
            self.log.error("Garbage JSON {} {}".format(ex, message))

    def handle_ProcessServerNatPacket(self, arguments):
        self.log.debug("handle_ProcessServerNatPacket {}".format(self))
        self.notify({
            'command_id': 'ProcessServerNatPacket',
            'arguments': arguments
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
                # This message is deprecated, since we tell players to connect to all peers at once
                pass  # pragma: no cover

            elif key == 'ConnectedToHost':
                # This message is deprecated, since we tell players to connect to all peers at once
                pass  # pragma: no cover

            elif key == 'Score':
                pass

            elif key == 'Bottleneck':
                # TODO: Use this for p2p reconnect
                pass

            elif key == 'BottleneckCleared':
                # TODO: Use this for p2p reconnect
                pass

            elif key == 'Desync':
                self.game.desyncs += 1

            elif key == 'ProcessNatPacket':
                # This is handled by subscription listeners
                pass

            elif key == 'GameState':
                state = values[0]
                yield from self.handle_game_state(state)

            elif key == 'GameOption':
                if values[0] == 'Victory':
                    self.game.gameOptions['Victory'] = Victory.from_gpgnet_string(values[1])
                elif values[0] in self.game.gameOptions:
                    self.game.gameOptions[values[0]] = values[1]

                if values[0] == "Slots":
                    self.game.maxPlayer = values[1]

                if values[0] == 'ScenarioFile':
                    raw = "%r" % values[1]
                    path = raw.replace('\\', '/')
                    mapname = str(path.split('/')[2]).lower()
                    curMap = self.game.mapName
                    if curMap != mapname:
                        self.game.setGameMap(mapname)
                        self.sendGameInfo()

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
                army = int(values[0])
                result = str(values[1])
                try:
                    if not any(map(functools.partial(str.startswith, result),
                            ['score', 'default', 'victory', 'draw'])):
                        raise ValueError()
                    result = result.split(' ')
                    self.game.add_result(self.player, army, result[0], int(result[1]))
                except (KeyError, ValueError):
                    self.log.warn("Invalid result for {} reported: {}".format(army, result))
                    pass

            elif key == 'Stats':
                # TODO: Log these
                pass

            elif key == 'Chat':
                # TODO: Send this to IRC for the game?
                pass

            elif key == 'OperationComplete':
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

                for player in self.game.players:
                    player.setAction("PLAYING")

                self.sendGameInfo()

                if len(self.game.mods) > 0:
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

                for player in self.game.players:
                    if player.global_rating.mu < -1000 or \
                       player.ladder_rating.mu < -1000:
                        self.game.setInvalid("You are playing with a smurfer.")

    def doEnd(self):
        """ bybye player :("""
        self.game.remove_game_connection(self)
        if self._state is GameConnectionState.ENDED:
            return
        else:
            self._state = GameConnectionState.ENDED

    def _send_create_lobby(self):
        """
        Used for initializing the game to start listening on UDP
        :param rankedMode int:
            If 1: The game uses autolobby.lua
               0: The game uses lobby.lua
        :return: None
        """
        if self.game is None:
            text = "You were unable to connect to the host because he has left the game."
            self.lobby.sendJSON(dict(command="notice",
                                     style="info",
                                     text=str(text)))
            self.abort()
            return

        if self.game.name is not None:
            if self.game.name.startswith('#'):
                self.sendToRelay("P2PReconnect", [])

        self.send_CreateLobby(self.game.init_mode,
                              self.player.gamePort,
                              self.player.login,
                              self.player.id, 1)

    def ConnectThroughProxy(self, peer, recurse=True):
        try:
            numProxy = self.game.proxy.map(self.player.login, peer.player.login)

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

    def sendGameInfo(self):
        self.games.mark_dirty(self.game.uuid)

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

    def on_connection_lost(self, exc):
        try:
            if self.game.proxy.unmap(self.player.login):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(PROXY_SERVER)
                s.sendall(json.dumps(dict(command="cleanup", sourceip=self.player.ip)))
                s.close()
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
        return "GameConnection(Player({}),Game({}))".format(self.player, self.game)
