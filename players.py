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


class Player(object):
    def __init__(self, login=None):
        
        self.uuid = 0
        self.session = 0
        self.login = ''
        self.ip = ''
        self.localIp = ''
      
      
      
        #social
        self.avatar = None
        self.clan = None
      
        self.league = None
      
        self.nomadsBeta = False
      
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
        
        self.udpFrom = []
        
       
        self.globalSkill = None
        self.ladder1v1Skill = None
        
        self.expandLadder = 0
        self.faction = 1
        
        self.wantToConnectToGame = False
        
        self.connectedToHost = False
        
        self.gameSocket = None

        self.UDPPacket = {}
        
        self.receivedUdp = False
        self.setPort = False


    def getLeague(self):
        return self.league
    
    def setLeague(self, league):
        self.league = int(league)

    def getFaction(self):
        return self.faction
    
    def setFaction(self, faction):
        if faction == "uef" :
            self.faction = 1
        elif faction == "aeon" :
            self.faction = 2
        elif faction == "cybran" :
            self.faction = 3
        elif faction == "seraphim" :
            self.faction = 4


    def getAvatar(self):
        return self.avatar
    
    def getClan(self):
        return self.clan

    def setUdpFrom(self, player):
        if not player in self.udpFrom :
            self.udpFrom.append(player)

    def removeUdpFrom(self, player):
        if player in self.udpFrom :
            self.udpFrom.remove(player)
            
    def receivedUdpFrom(self, player):
        if player in self.udpFrom :
            return True
        return False


    def getUdpPacketPort(self) :
        return self.udpPacketPort
            
    def setUdpPacketPort(self, port) :
        self.udpPacketPort = int(port)
    
    def resetUdpFrom(self):
        self.udpFrom = []

    def getReceivedUdp(self):
        return self.receivedUdp

    def setReceivedUdp(self, state):
        self.receivedUdp = state

    def resetUdpPacket(self):
        self.UDPPacket.clear()

    def countUdpPacket(self, address):
        if address in self.UDPPacket :
            return self.UDPPacket[address]
        else :
            return 0

    def addCountUdpPacket(self, address):
        if address in self.UDPPacket :
            self.UDPPacket[address] = self.UDPPacket[address] + 1 
        else :
            self.UDPPacket[address] = 1
        
        

    def setGameSocket(self, socket):
        if socket != 0 :
            self.gameSocket = socket
        else :
            self.gameSocket = None

    def getGameSocket(self):
        return self.gameSocket

    def getWantGame(self):
        return self.wantToConnectToGame

    def setWantGame(self, value):
        self.wantToConnectToGame = value


    def getExpandLadder(self):
        return self.expandLadder 

    def setExpandLadder(self, value):
        
        self.expandLadder = value
        return 1
    
    def isConnectedToHost(self):
        return self.connectedToHost
    
    def connectedToHost(self, value):
        if value == 1 :
            self.connectedToHost = True
        else :
            self.connectedToHost = False
    
    def getLobbyThread(self):
        return self.lobbyThread
         
    def setupPlayer(self, session, login, ip, port, localIp, uuid, globalSkill, trueSkill1v1, numGames, lobbyThread ):
        
        self.numGames = numGames
        self.session = session
        self.login = login
        self.ip = ip
        self.gamePort = port
        self.uuid = uuid
        self.localIp = localIp
        self.lobbyThread = lobbyThread
        self.globalSkill = globalSkill
        self.ladder1v1Skill = trueSkill1v1

    def getNumGames(self):
        return self.numGames

    def setRating(self, rating):
        self.globalSkill.setRating(self.globalSkill.getPlayer(), rating)

    
    def setladder1v1Rating(self, rating):
        self.ladder1v1Skill.setRating(self.ladder1v1Skill.getPlayer(), rating)

    def getRating(self):
        return self.globalSkill

    def getladder1v1Rating(self):
        return self.ladder1v1Skill

    def setGamePort(self, gamePort):
        if gamePort == 0 :
            gamePort = 6112
        self.gamePort = gamePort
         
        #self.localGamePort = gamePort

        return 1
    
    def setLogin(self, login):
        self.login = str(login)
    
    def setGame(self, gameName):
        if gameName == '' :
            return 0
        self.game = gameName
        return 1

    def setAction(self, action):
        if action == '' :
            return 0
        self.action = action
        return 1

    def getGamePort(self):
        return self.gamePort

    def getLocalGamePort(self):
        return self.localGamePort
    
    def getGame(self):
        return str(self.game)
    
    def getAction(self):
        return str(self.action)

    def getAddress(self):
        return "%s:%s" % (str(self.getIp()), str(self.getGamePort()))

    def getLocalAddress(self):
        return "%s:%s" % (str(self.getLocalIp()), str(self.getLocalGamePort()))

    def getIp(self):
        return self.ip

    def getLocalIp(self):
        return self.localIp
     
    def getLogin(self):
        return str(self.login)
    
    def getId(self):
        return self.uuid

    def getSession(self):
        return self.session

class playersOnline(object):
    def __init__(self, parent = None):
        self.players = []
        self.logins = []
        
        
    def getAllPlayers(self):
        return self.players

    def getNumPlayers(self):
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
                if newplayer.getSession() == player.getSession() :
                    # uuid is the same, I don't know how it's possible, but we do nothing.
                    return gamesocket, lobbySocket
                
                if newplayer.getLogin() == player.getLogin() :
                    # login exists, uuid not the same
                    
                    try :
                        gamesocket = player.getGameSocket()
    
                        lobbyThread = player.getLobbyThread()
                        if lobbyThread != None :
                            lobbySocket = lobbyThread.socket
                         
                        
                        #self.players.remove(player)
                        
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
            if player.getLogin() == name :
                return player
        return 0
    
    def findByIp(self, ip):
        for player in self.players:
            if player.ip == ip and player.getWantGame():
                return player
        return None

    def checkSession(self, login, session):
        for player in self.players:
                return 1
        return 0
               
   
    def list(self):
        pass
        # for player in self.players:
            # print ("uuid : " + str(player.uuid))
            # print ("login :" + player.login)
            # print ("ip : " + player.ip)
            # print ("game port : " + str(player.gamePort))