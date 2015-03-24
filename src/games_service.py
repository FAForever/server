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

import logging

from src.games import Game


class GamesService(object):
    """
    Utility class for maintaining lifecycle of games
    """
    def __init__(self, players, db):
        
        self._dirty_games = []
        self.players = players
        self.db = db
        
        self.log = logging.getLogger(__name__)

        if not self.db.isOpen():
            self.db.open()
        
        self.gamesContainer = {}

    @property
    def dirty_games(self):
        return self._dirty_games

    def clear_dirty(self):
        self._dirty_games = []

    def addContainer(self, name, container):
        """ add a game container class named <name>"""
        if not name in self.gamesContainer:
            self.gamesContainer[name] = container
            return 1
        return 0

    def isaContainer(self, name):
        if name in self.gamesContainer :
            return True
        return False        


    def create_game(self, access, name, player, gameName, gamePort, mapname, password=None):
        container = self.getContainer(name)
        if container:
            game = container.addBasicGame(player, gameName, gamePort)
            if game:
                game.setGameMap(mapname)
                game.setAccess(access)
                if password is not None:
                    game.setPassword(password)
                self.mark_dirty(game.id)
                return game
        return None

    def mark_dirty(self, game_id):
        self._dirty_games.append(game_id)

    def sendGamesList(self):
        games = []
        for key, container in self.gamesContainer :
            
            if container.listable :

                for game in container.games :
                    if game.lobbyState == "open" :
                        
                        json = {
                            "command": "game_info",
                            "uid": game.uuid,
                            "title": game.gameName,
                            "state": game.lobbyState,
                            "featured_mod": game.getGamemod(),
                            "mapname": game.mapName.lower(),
                            "host": game.hostPlayer,
                            "num_players": len(game.players),
                            "game_type": game.gameType
                        }

                        teams = game.teamAssign
    
                        teamsToSend = {}
                        for k, v in teams.items() :
                            if len(v) != 0 :
                                teamsToSend[k] = v
    
                        json["teams"] = teamsToSend

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

    def find_by_id(self, uuid):
        """
        :rtype: Game
        """
        for container in self.gamesContainer:
            game = self.gamesContainer[container].findGameByUuid(str(uuid))
            if game is not None:
                return game
        return None    
