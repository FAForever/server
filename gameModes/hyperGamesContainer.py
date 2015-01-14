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

from customGamesContainer import customGamesContainerClass
from ladderGamesContainer import ladder1v1GamesContainerClass
import sys, inspect, logging

class hyperGamesContainerClass(object):
    '''Class for containing all games containers'''
    
    def __init__(self, players, db, dirtyGameList, parent = None):
        
        self.dirtyGameList = dirtyGameList
        self.players = players
        self.db = db
        
        self.log = logging.getLogger(__name__)
        
        self.log.debug("HyperGameContainer initialized")
        
        if not self.db.isOpen():
            self.db.open()
        
        self.gamesContainer = {}
        
    def setContainerDescription(self, name, desc):
        if name in self.gamesContainer :
            self.gamesContainer[name].setDesc(desc)
            return

    def addContainer(self, name, container) :
        ''' add a game container class named <name>'''
        if not name in self.gamesContainer :
            self.gamesContainer[name] = container
            return 1
        return 0

    def reloadAllContainer(self, force = True):
        for name in self.gamesContainer :
            self.reloadContainer(name, force)

    def reloadContainer(self, name, force = False):
        ''' reload the container named <name>'''
        if not name in self.gamesContainer :
            return False
        
        container = self.gamesContainer[name]
        curVersion = container.version
        self.log.info("Current container version : " + str(curVersion))
        
        module = sys.modules[container.__module__]
        reload(module)
        classCont = type(container).__name__

        for nameClass, obj in inspect.getmembers(module):
            if nameClass == classCont :
                newContainer = obj(container.db, self)
                
                if newContainer.version > curVersion or force == True :
                    self.log.info("Replacing container " + name + " with version " + str(newContainer.version))
                    #we replace it
                    self.gamesContainer.pop(name)
                    self.addContainer(name, newContainer)
                    
                    return True
                else :
                    return False
        return False

    def isaContainer(self, name):
        if name in self.gamesContainer :
            return True
        return False        

    def renameContainer(self, fromname, toname):
        if fromname in self.gamesContainer :
            if not toname in self.gamesContainer :
                self.gamesContainer[fromname].renameMod(toname)
                self.gamesContainer[toname] = self.gamesContainer[fromname]
                del self.gamesContainer[fromname]
        

#    def addHost(self, host, type):
#        ''' add a host hosting a game type'''
#        if str(type) in self.gamesContainer :
#            self.hosts[str(host)] = str(type)
#            return 1
#        return 0


    def removePlayer(self, player):
        for container in self.gamesContainer :
           
            if hasattr(self.gamesContainer[container], "removePlayer") :
                self.gamesContainer[container].removePlayer(player)
        

    def addGame(self, access, name, player, gameName, gamePort, mapname, password = None):
        container = self.getContainer(name)
        if container != None :
            game = container.addBasicGame(player, gameName, gamePort)
            if game != False :
                game.setGameMap(mapname)
                game.setAccess(access)
                if password != None :
                    game.setPassword(password)
                
                return game
        return None



    def sendGamesList(self):
        games = []
        for container in self.gamesContainer :
            
            if self.gamesContainer[container].isListable() == True :

                for game in self.gamesContainer[container].getGames() :
                    if game.getLobbyState() == "open" :
                        
                        json = {}
                        json["command"] = "game_info"
                        json["uid"] = game.getuuid()
                        json["title"] = game.getGameName()
                        json["state"] = game.getLobbyState()
                        json["featured_mod"]= game.getGamemod()
                        json["mapname"] = game.getMapName().lower()
                        json["host"] = game.getHostName()
                        json["num_players"] = game.getNumPlayer()
                        json["game_type"] = game.getGameType()
    

                        teams = game.getTeamsAssignements()
    
                        teamsToSend = {}
                        for k, v in teams.iteritems() :
                            if len(v) != 0 :
                                teamsToSend[k] = v
    
    
                        json["teams"] = teamsToSend
    
    
                        #self.recombineTeams()
    
    
                        #quality = self.getMatchQuality()
                        #if quality != None :
                         #   json["quality"] = quality
    

                        games.append(json) 

        return games
    
    def removeOldGames(self):
        for container in self.gamesContainer :
            self.gamesContainer[container].removeOldGames()
        return True

    def getContainer(self, name):
        if name in self.gamesContainer :
            return self.gamesContainer[name]
        return None

    def getGameContainer(self, game):
        for container in self.gamesContainer :
            if game in self.gamesContainer[container].getGames() :
                return self.gamesContainer[container]
        return True        

    def removeGame(self, game):
        for container in self.gamesContainer :
            self.gamesContainer[container].removeGame(game)
        return True
    
    def removeUserGame(self, player):
        for container in self.gamesContainer :
            self.gamesContainer[container].removeUserGame(player)
        return True
    

    def getGameByUuid(self, uuid):
        '''Get a game by his uuid'''
        for container in self.gamesContainer :
            game = self.gamesContainer[container].findGameByUuid(str(uuid))
            if game != None :
                return game
        return None    
    
    def getGameByHost(self, host):
        '''Get a game by the name of the host'''
        for container in self.gamesContainer :
            game = self.gamesContainer[container].findGameByHost(str(host))
            if game != None :
                return game
        return None
