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

from .abc.base_player import BasePlayer


class Player(BasePlayer):
    """
    Standard player object used for representing signed-in players.

    In the context of a game, the Game object holds game-specific
    information about players.
    """
    def __init__(self, login=None):
        super().__init__()
        
        self._action = ''
        self.uuid = 0
        self.session = 0
        self._login = login
        self._ip = ''
        self.localIp = ''

        #social
        self.avatar = None
        self.clan = None
      
        self.league = None
      
        self.admin = False
        self.mod = False
        
        self.numGames = 0
        self.gamePort = 0

        self.localGamePort = 0
        self.udpPacketPort = 0

        self.action = "NOTHING"
        self.game = ''
        self.lobbyThread = None
        self.gameThread = None
        
        self.globalSkill = None
        self.ladder1v1Skill = None
        self.expandLadder = 0
        self.faction = 1
        self.wantToConnectToGame = False


    def setupPlayer(self, session, login, ip, port, localIp, uuid, globalSkill, trueSkill1v1, numGames, lobbyThread ):
        self.numGames = numGames
        self.session = session
        self._login = login
        self._ip = ip
        self.gamePort = port
        self.uuid = uuid
        self.localIp = localIp
        self.lobbyThread = lobbyThread
        self.globalSkill = globalSkill
        self.ladder1v1Skill = trueSkill1v1

    def setGamePort(self, gamePort):
        if gamePort == 0 :
            gamePort = 6112
        self.gamePort = gamePort

        return 1
    
    def setLogin(self, login):
        self._login = str(login)
    
    def setGame(self, gameName):
        if gameName == '' :
            return 0
        self.game = gameName
        return 1

    def getLocalGamePort(self):
        return self.localGamePort
    
    def getGame(self):
        return str(self.game)

    @property
    def action(self):
        return self._action

    @action.setter
    def action(self, value):
        self._action = value
    
    def getAction(self):
        return str(self._action)

    def setAction(self, action):
        if action == '' :
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
    def id(self):
        return self.uuid

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


class PlayersOnline(object):
    def __init__(self):
        self.players = []
        self.logins = []

    def __len__(self):
        return len(self.players)

    def addUser(self, newplayer):
        gamesocket = None
        lobbySocket = None
        # login not in current active players
        if not newplayer.getLogin() in self.logins:
            self.logins.append(newplayer.getLogin())
            self.players.append(newplayer)
            return gamesocket, lobbySocket
        else :
            # login in current active player list !
            
            for player in self.players:
                if newplayer.session == player.session :
                    # uuid is the same, I don't know how it's possible, but we do nothing.
                    return gamesocket, lobbySocket
                
                if newplayer.getLogin() == player.getLogin():
                    # login exists, uuid not the same
                    try :
                        lobbyThread = player.lobbyThread
                        if lobbyThread is not None:
                            lobbySocket = lobbyThread.socket
                    except :
                        pass
                        
                    self.players.append(newplayer)
                    self.logins.append(newplayer.login)

                    return gamesocket, lobbySocket


    def removeUser(self, player):
        if player.getLogin() in self.logins:
            self.logins.remove(player.login)
            if player in self.players :
                self.players.remove(player)
                #del player
            return 1
        else :
            return 0

    def findByName(self, name):
        for player in self.players:
            if player.getLogin() == name:
                return player
        return 0
    
    def findByIp(self, ip):
        for player in self.players:
            if player.ip == ip and player.wantToConnectToGame:
                return player
        return None
