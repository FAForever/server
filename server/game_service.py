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
from server import games

from server.decorators import with_logger

from server.games.game import Game


@with_logger
class GameService:
    """
    Utility class for maintaining lifecycle of games
    """
    def __init__(self, players, db):
        self._dirty_games = set()
        self.players = players
        self.db = db
        self._containers = {}
        self.add_game_modes()

    @property
    def dirty_games(self):
        return self._dirty_games

    def clear_dirty(self):
        self._dirty_games = set()

    def add_game_modes(self):
        for name, nice_name, container in games.game_modes:
            self._containers[name] = container(name=name,
                                               nice_name=nice_name,
                                               db=self.db,
                                               games_service=self)

    def create_game(self,
                    visibility='public',
                    game_mode=None,
                    host=None,
                    name=None,
                    mapname=None,
                    password=None,
                    version=None):
        container = self.getContainer(game_mode)
        if container:
            game = container.addBasicGame(host, name)
            if game:
                game.setGameMap(mapname)
                game.setAccess(visibility)
                if password is not None:
                    game.setPassword(password)
                self.mark_dirty(game)
                return game
        return None

    def mark_dirty(self, game):
        self._dirty_games.add(game)

    def getContainer(self, name):
        if name in self._containers:
            return self._containers[name]
        return None

    def find_by_id(self, id):
        """
        Look up a game by ID
        :rtype: Game
        """
        for container in self._containers:
            game = self._containers[container].findGameByUuid(id)
            if game is not None:
                return game
        return None    
