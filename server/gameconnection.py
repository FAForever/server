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
from concurrent.futures import CancelledError
import socket
import time
import logging
import functools

from PySide.QtSql import *
import json
import config

from server.abc.base_game import GameConnectionState
from server.connectivity import TestPeer, ConnectivityState
from server.games.game import Game, GameState, Victory
from server.decorators import with_logger, timed
from server.game_service import GameService
from server.protocol.gpgnet import GpgNetServerProtocol
from server.subscribable import Subscribable


logger = logging.getLogger(__name__)


PROXY_SERVER = ('127.0.0.1', 12000)

@with_logger
class GameConnection(Subscribable, GpgNetServerProtocol):
    """
    Responsible for connections to the game, using the GPGNet protocol
    """
    def __init__(self, loop, users, games: GameService, db, db_pool):
        """
        Construct a new GameConnection

        :param loop: asyncio event loop to use
        :param users: PlayersOnline
        :param games: GamesService
        :param db: QSqlDatabase
        :param db_pool: aiomysql connection pool
        :return:
        """
        super().__init__()
        self.protocol = None
        self._logger.info('GameConnection initializing')
        self._state = GameConnectionState.INITIALIZING
        self.loop = loop
        self.users = users
        self.games = games

        self.db = db
        self.db_pool = db_pool
        self.log = logging.getLogger(__name__)
        self.initTime = time.time()
        self.proxies = {}
        self._player = None
        self.logGame = "\t"
        self._game = None

        self.last_pong = time.time()

        self._authenticated = asyncio.Future()
        self.ip, self.port = None, None
        self.lobby = None
        self._transport = None
        self.nat_packets = {}
        self.ping_task = None
        self._connectivity_state = None

        self.connectivity_state = asyncio.Future()

    @property
    def state(self):
        """
        :rtype: GameConnectionState
        """
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

    @property
    def player(self):
        return self._player

    @player.setter
    def player(self, val):
        self._player = val

    @asyncio.coroutine
    def on_connection_made(self, protocol, peer_name):
        """
        Accept a connected socket for this GameConnection

        Will look up the user using the provided users service,
        followed by obtaining the Game object that the user wishes to join.
        :raise AssertionError
        :return: bool
        """
        self._logger.debug("Accepting connection from {}".format(peer_name))
        self.protocol = protocol
        (self.ip, self.port) = peer_name

    @asyncio.coroutine
    def authenticate(self, session):
        """
        Perform very rudimentary authentication.

        For now, this exists primarily to avoid conditions with players,
        behind the same public address which would cause problems with the old design.
        """
        try:
            self._player = self.users.find_by_ip_and_session(self.ip, session)
            self.log.debug("Resolved user to {} through lookup by {}:{}".format(self.player, self.ip, session))

            if self.player is None:
                self.log.info("Player not found for IP: %s " % self.ip)
                self.abort()
                return

            if self.player.game is None:
                self.log.info("Player hasn't indicated that he wants to join a game")
                self.abort()
                return

            self.game = self.player.game
            self.player.game_connection = self
            self.lobby = self.player.lobby_connection

            self.player.setPort = False
            self.player.connectedToHost = False

            self.ping_task = asyncio.async(self.ping())
            self.player.wantToConnectToGame = False
            self._state = GameConnectionState.INITIALIZED
            self._authenticated.set_result(session)
        except (CancelledError, asyncio.InvalidStateError) as ex:
            self._logger.exception(ex)
            self.abort()

    def send_message(self, message):
        self.protocol.send_message(message)

    @asyncio.coroutine
    def ping(self):
        """
        Ping the relay server to check if the player is still there.
        """
        while True:
            if self._state == GameConnectionState.ENDED:
                break
            if time.time() - self.last_pong > 30:
                self._logger.debug('Missed ping, terminating')
                self.abort()
                break
            self.send_Ping()
            try:
                yield from asyncio.sleep(20)
            # quamash will yield a runtime error if the qtimer was already deleted
            # asyncio yields a cancelled error which we use to break the loop
            except (RuntimeError, CancelledError):  # pragma: no cover
                break

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
            self.game.host = self.player
            strlog = (
                "%s.%s.%s\t" % (str(self.player.getLogin()), str(self.game.uuid), str(self.game.gamemod)))
            self.logGame = strlog
            self._send_create_lobby()

        elif action == "JOIN":
            strlog = (
                "%s.%s.%s\t" % (str(self.player.getLogin()), str(self.game.uuid), str(self.game.gamemod)))
            self.logGame = strlog
            self._send_create_lobby()

        else:
            self.log.debug("QUIT - No player action :(")
            self.abort()

    @asyncio.coroutine
    def _handle_lobby_state(self):
        """
        The game has told us it is ready and listening on
        self.player.gamePort for UDP.
        We determine the connectivity of the peer and respond
        appropriately
        """
        try:
            with TestPeer(self,
                          self.player.ip,
                          self.player.game_port,
                          self.player.id) as peer_test:
                self._connectivity_state = yield from peer_test.determine_connectivity()
                self.connectivity_state.set_result(self._connectivity_state)
                self.send_gpgnet_message('ConnectivityState', [self.player.getId(),
                                                       self._connectivity_state.state.value])

            playeraction = self.player.action
            if playeraction == "HOST":
                map = self.game.mapName
                self.send_HostGame(map)
            # If the player is joining, we connect him to host
            # followed by the rest of the players.
            elif playeraction == "JOIN":
                yield from self.ConnectToHost(self.game.host.game_connection)
                self._state = GameConnectionState.CONNECTED_TO_HOST
                self.game.add_game_connection(self)
                for peer in self.game.connections:
                    if peer != self and peer.player != self.game.host:
                        self.log.debug("{} connecting to {}".format(self.player, peer))
                        asyncio.async(self.ConnectToPeer(peer))
        except Exception as e:
            self.log.exception(e)

    @asyncio.coroutine
    @timed(limit=0.1)
    def on_message_received(self, message):
        """
        Main entry point when reading messages
        :param message:
        :return:
        """
        try:
            message["command_id"] = message['action']
            message["arguments"] = message['chuncks']
            yield from self.handle_action(message["action"], message["chuncks"])
            self.notify(message)
        except ValueError as ex:  # pragma: no cover
            self.log.error("Garbage command {} {}".format(ex, message))

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
        connection, own_addr, peer_addr = yield from self.EstablishConnection(peer)
        if connection == ConnectivityState.PUBLIC or connection == ConnectivityState.STUN:
            self.send_JoinGame(peer_addr,
                               peer.player.login,
                               peer.player.id)
            peer.send_ConnectToPeer(own_addr,
                                    self.player.login,
                                    self.player.id)
        else:
            self.ConnectThroughProxy(peer)

    @asyncio.coroutine
    def ConnectToPeer(self, peer):
        """
        Connect two peers
        :return: None
        """
        connection, own_addr, peer_addr = yield from self.EstablishConnection(peer)
        if connection == ConnectivityState.PUBLIC or connection == ConnectivityState.STUN:
            self.send_ConnectToPeer(peer_addr,
                                    peer.player.login,
                                    peer.player.id)
            peer.send_ConnectToPeer(own_addr,
                                    self.player.login,
                                    self.player.id)
        else:
            self.ConnectThroughProxy(peer)

    @asyncio.coroutine
    def EstablishConnection(self, peer):
        """
        Attempt to establish a full duplex UDP connection
        between self and peer.

        :param peer: Client to connect to
        :return: (ConnectivityState, own_addr, remote_addr)
        """
        own_state = self.connectivity_state
        peer_state = peer.connectivity_state
        (done, pending) = yield from asyncio.wait([own_state, peer_state])
        if pending:
            self._logger.debug("Aborting due to lack of connectivity")
            self.abort()
        ((own_addr, own_state), (peer_addr, peer_state)) = own_state.result(), peer_state.result()
        if peer_state == ConnectivityState.PUBLIC and own_state == ConnectivityState.PUBLIC:
            self._logger.debug("Connecting {} to host {} directly".format(self, peer))
            return ConnectivityState.PUBLIC, own_addr, peer_addr
        elif peer_state == ConnectivityState.STUN or own_state == ConnectivityState.STUN:
            self._logger.debug("Connecting {} to host {} using STUN".format(self, peer))
            (own_addr, peer_addr) = yield from self.STUN(peer)
            if peer_addr is None or own_addr is None:
                self._logger.debug("STUN between {} {} failed".format(self, peer))
                self._logger.debug("Resolved addresses: {}, {}".format(peer_addr, own_addr))
                self._logger.debug("Own nat packets: {}".format(self.nat_packets))
                self._logger.debug("Peer nat packets: {}".format(peer.nat_packets))
            else:
                return ConnectivityState.STUN, own_addr, peer_addr
        self._logger.debug("Connecting {} to host {} through proxy".format(self, peer))
        return ConnectivityState.PROXY, None, None

    @asyncio.coroutine
    def STUN(self, peer):
        """
        Perform a STUN sequence between self and peer

        :param peer:
        :return: (own_addr, remote_addr) | None
        """
        own_addr = asyncio.async(self.ProbePeerNAT(peer))
        remote_addr = asyncio.async(peer.ProbePeerNAT(self))
        (done, pending) = yield from asyncio.wait([own_addr, remote_addr])
        assert len(pending) == 0
        assert len(done) == 2
        own_addr, remote_addr = own_addr.result(), remote_addr.result()
        if own_addr is not None and remote_addr is not None:
            # Both peers got it the first time
            return own_addr, remote_addr
        if own_addr is not None:
            # Remote received our packet, we didn't receive theirs
            # Instruct remote to try our new address
            remote_addr = yield from peer.ProbePeerNAT(self, use_address=own_addr)
        elif remote_addr is not None:
            # Opposite of the above
            own_addr = yield from self.ProbePeerNAT(peer, use_address=remote_addr)
        return own_addr, remote_addr

    @asyncio.coroutine
    def ProbePeerNAT(self, peer, use_address=None):
        """
        Instruct self to send an identifiable nat packet to peer

        :return: resolved_address
        """
        nat_message = "Hello from {}".format(self.player.id)
        addr = peer.connectivity_state.result()[0] if not use_address else use_address
        self._logger.debug("{} probing {} at {} with msg: {}".format(self, peer, addr, nat_message))
        for _ in range(2):
            self.send_SendNatPacket(addr, nat_message)
        try:
            received_message = asyncio.Future()
            peer.nat_packets[nat_message] = received_message
            yield from asyncio.wait_for(received_message, 4)
            return received_message.result()
        except (CancelledError, asyncio.TimeoutError):
            return None

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
        try:
            if key == 'Authenticate':
                yield from self.authenticate(int(values[0]))
            elif not self._authenticated.done():
                @asyncio.coroutine
                def queue_until_authed():
                    yield from self._authenticated
                    yield from self.handle_action(key, values)
                asyncio.async(queue_until_authed())
                return
            elif key == 'pong':
                self.last_pong = time.time()
                return

            elif key == 'ProcessNatPacket':
                address, message = values[0], values[1]
                self._logger.info("{}.ProcessNatPacket: {} {}".format(self, values[0], values[1]))
                if message in self.nat_packets and isinstance(self.nat_packets[message], asyncio.Future):
                    if not self.nat_packets[message].done():
                        self.nat_packets[message].set_result(address)

            elif key == 'Desync':
                self.game.desyncs += 1

            elif key == 'GameState':
                state = values[0]
                yield from self.handle_game_state(state)
                self._mark_dirty()

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
                self._mark_dirty()

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
                self._mark_dirty()

            elif key == 'PlayerOption':
                if self.player.action == "HOST":
                    id = values[0]
                    key = values[1]
                    value = values[2]
                    self.game.set_player_option(int(id), key, value)
                    self._mark_dirty()

            elif key == 'AIOption':
                if self.player.action == "HOST":
                    name = values[0]
                    key = values[1]
                    value = values[2]
                    self.game.set_ai_option(str(name), key, value)
                    self._mark_dirty()

            elif key == 'ClearSlot':
                if self.player.action == "HOST":
                    slot = values[0]
                    self.game.clear_slot(slot)
                self._mark_dirty()

            elif key == 'GameResult':
                army = int(values[0])
                result = str(values[1])
                try:
                    if not any(map(functools.partial(str.startswith, result),
                            ['score', 'default', 'victory', 'draw'])):
                        raise ValueError()  # pragma: no cover
                    result = result.split(' ')
                    self.game.add_result(self.player, army, result[0], int(result[1]))
                except (KeyError, ValueError):  # pragma: no cover
                    self.log.warn("Invalid result for {} reported: {}".format(army, result))
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

        except Exception as e:  # pragma: no cover
            self.log.exception(e)
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
            #
            # We do not yield from the task, since we
            # need to keep processing other commands while it runs
            asyncio.async(self._handle_lobby_state())

        elif state == 'Launching':
            if self.player.action == "HOST":
                self.game.launch()

                if len(self.game.mods) > 0:
                    for uid in self.game.mods:
                        query = QSqlQuery(self.db)
                        query.prepare("UPDATE `table_mod` SET `played`= `played`+1  WHERE uid = ?")
                        query.addBindValue(uid)
                        query.exec_()

                for player in self.game.players:
                    if player.global_rating[0] < -1000 or \
                       player.ladder_rating[0] < -1000:
                        self.game.mark_invalid("You are playing with a smurfer.")

    def _send_create_lobby(self):
        """
        Used for initializing the game to start listening on UDP
        :param rankedMode int:
            If 1: The game uses autolobby.lua
               0: The game uses lobby.lua
        :return: None
        """
        assert self.game is not None
        if self.game.name is not None:
            if self.game.name.startswith('#'):
                self.send_gpgnet_message("P2PReconnect", [])

        self.send_CreateLobby(self.game.init_mode,
                              self.player.gamePort,
                              self.player.login,
                              self.player.id, 1)

    def ConnectThroughProxy(self, peer, recurse=True):
        try:
            numProxy = self.game.proxy.map(self.player.login, peer.player.login)

            if numProxy is not None:
                self.send_ConnectToProxy(numProxy, peer.player.getIp(), str(peer.player.login), int(peer.player.id))

                if self.game:
                    self.game._logger.debug("%s is connecting through proxy to %s on port %i" % (
                        self.player.login, peer.player.login, numProxy))

                if recurse:
                    peer.ConnectThroughProxy(self, False)
            else:
                self.log.debug(self.logGame + "Maximum proxies used")  # pragma: no cover
        except Exception as e:  # pragma: no cover
            self.log.exception(e)

    def _mark_dirty(self):
        self.games.mark_dirty(self.game)

    def abort(self):
        """
        Abort the connection

        Removes the GameConnection object from the any associated Game object,
        and deletes references to Player and Game held by this object.
        """
        try:
            if self._state is GameConnectionState.ENDED:
                return
            self._state = GameConnectionState.ENDED
            if self.game:
                self.game.remove_game_connection(self)
            self._mark_dirty()
            self.log.debug("{}.abort()".format(self))
            del self.player.game
            del self.player.game_connection
        except Exception as ex:  # pragma: no cover
            self.log.debug("Exception in abort(): {}".format(ex))
            pass
        finally:
            if self.ping_task is not None:
                self.ping_task.cancel()
            if self._player:
                self._player.action = 'NONE'

    def on_connection_lost(self):
        try:
            if self.state == GameConnectionState.CONNECTED_TO_HOST\
                    and self.game.state == GameState.LOBBY:
                for peer in self.game.connections:
                    peer.send_DisconnectFromPeer(self.player.id)
            if self.game:
                if self.game.proxy.unmap(self.player.login):
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(PROXY_SERVER)
                    s.sendall(json.dumps(dict(command="cleanup", sourceip=self.player.ip)).encode())
                    s.close()
            if self.connectivity_state.done()\
                    and self.connectivity_state.result() == ConnectivityState.PROXY:
                wiki_link = "{}index.php?title=Connection_issues_and_solutions".format(config.WIKI_LINK)
                text = "Your network is not setup right.<br>The server had to make you connect to other players by proxy.<br>Please visit <a href='{}'>{}</a>" + \
                       "to fix this.<br><br>The proxy server costs us a lot of bandwidth. It's free to use, but if you are using it often,<br>it would be nice to donate for the server maintenance costs,".format(wiki_link, wiki_link)

                self.lobby.sendJSON(dict(command="notice", style="info", text=str(text)))
        except Exception as e:  # pragma: no cover
            self._logger.exception(e)
            pass
        finally:
            self.abort()

    def connectivity_state(self):
        return self._connectivity_state

    def address_and_port(self):
        return "{}:{}".format(self.player.getIp(), self.player.gamePort)

    def __str__(self):
        return "GameConnection(Player({}),Game({}))".format(self.player, self.game)
