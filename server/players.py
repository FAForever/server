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
import weakref

from .abc.base_player import BasePlayer


class Player(BasePlayer):
    """
    Standard player object used for representing signed-in players.

    In the context of a game, the Game object holds game-specific
    information about players.
    """
    def __init__(self, login=None, session=0, ip=None, port=None, uuid=0,
                 global_rating=(1500, 500), ladder_rating=(1500, 500), clan=None, numGames=0, lobbyThread=None):
        super().__init__()
        
        self._action = ''
        self.uuid = uuid
        self.session = session
        self._login = login
        self._ip = ''
        self.localIp = ''

        self.global_rating = global_rating
        self.ladder_rating = ladder_rating

        #social
        self.avatar = None
        self.clan = clan
        self.country = None

        self.league = None
        self.leagueInfo = None
      
        self.admin = False
        self.mod = False
        
        self.numGames = numGames
        self.gamePort = 0

        self.localGamePort = 0
        self.udpPacketPort = 0

        self.action = "NOTHING"

        self.globalSkill = None
        self.ladder1v1Skill = None
        self.expandLadder = 0
        self.faction = 1
        self.wantToConnectToGame = False

        self._login = login
        self._ip = ip
        self.gamePort = port

        self._lobby_connection = lambda: None
        if lobbyThread is not None:
            self.lobby_connection = lobbyThread

        self._game = lambda: None
        self._game_connection = lambda: None

    def setGamePort(self, gamePort):
        if gamePort == 0:
            gamePort = 6112
        self.gamePort = gamePort

        return 1

    def setLogin(self, login):
        self._login = str(login)

    def getLocalGamePort(self):
        return self.localGamePort

    @property
    def action(self):
        return self._action

    @action.setter
    def action(self, value):
        self._action = value
    
    def getAction(self):
        return str(self._action)

    def setAction(self, action):
        if action == '':
            return 0
        self._action = action
        return 1

    def getAddress(self):
        return "%s:%s" % (str(self.getIp()), str(self.gamePort))

    def getLocalAddress(self):
        return "%s:%s" % (str(self.getLocalIp()), str(self.getLocalGamePort()))

    def getIp(self):
        return self._ip

    def getLocalIp(self):
        return self.localIp
     
    def getLogin(self):
        return str(self._login)
    
    def getId(self):
        return self.uuid

    @property
    def lobbyThread(self):
        return self.lobby_connection

    @property
    def lobby_connection(self):
        """
        Weak reference to the LobbyConnection of this player
        """
        return self._lobby_connection()

    @lobby_connection.setter
    def lobby_connection(self, value):
        self._lobby_connection = weakref.ref(value)

    @property
    def game(self):
        """
        Weak reference to the Game object that this player wants to join or is currently in
        """
        return self._game()

    @game.setter
    def game(self, value):
        self._game = weakref.ref(value)

    @property
    def game_connection(self):
        """
        Weak reference to the GameConnection object for this player
        :return:
        """
        return self._game_connection()

    @game_connection.setter
    def game_connection(self, value):
        self._game_connection = weakref.ref(value)

    @property
    def id(self):
        return int(self.uuid)

    @property
    def ip(self):
        return self.getIp()

    @property
    def login(self):
        return self._login

    @property
    def game_port(self):
        return self.gamePort

    @property
    def address_and_port(self):
        return "{}:{}".format(self.ip, self.game_port)

    @login.setter
    def login(self, value):
        self._login = value

    def to_dict(self):
        """
        Return a dictionary representing this player object
        :return:
        """
        def filter_none(t):
            _, v = t
            return v is not None
        return dict(filter(filter_none, (
            ('command', 'player_info'),
            ('login', self.login),
            ('rating_mean', self.global_rating[0]),
            ('rating_deviation', self.global_rating[1]),
            ('ladder_rating_mean', self.ladder_rating[0]),
            ('ladder_rating_deviation', self.ladder_rating[1]),
            ('number_of_games', self.numGames),
            ('avatar', self.avatar),
            ('league', self.leagueInfo),
            ('country', self.country),
            ('clan', self.clan)
        )))

    def __hash__(self):
        return self.id

    def __eq__(self, other):
        if not isinstance(other, BasePlayer):
            return False
        else:
            return self.id == other.id
