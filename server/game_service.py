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
from server.players import Player


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

    def mark_dirty(self, game):
        self._dirty_games.add(game)

    def clear_dirty(self):
        self._dirty_games = set()

    def add_game_modes(self):
        for name, nice_name, container in games.game_modes:
            self._containers[name] = container(name=name,
                                               nice_name=nice_name,
                                               db=self.db,
                                               games_service=self)

    def create_game(self,
                    visibility: str='public',
                    game_mode: str=None,
                    host: Player=None,
                    name: str=None,
                    mapname: str=None,
                    password: str=None,
                    version=None):
        """
        Main entrypoint for creating new games
        """
        if game_mode not in self._containers:
            raise KeyError("Unknown gamemode: {}".format(game_mode))
        try:
            game = self._containers[game_mode].addBasicGame(host, name)
        except AttributeError:
            raise ValueError('Container {} cannot be used this way'.format(game_mode))
        if not game:
            raise ValueError('Container {} refused to make game: {}'.format(game_mode, game))
        self._logger.info("{} created in {} container".format(game, game_mode))
        game.mapName = mapname
        game.access = visibility
        game.version = version

        if password is not None:
            game.password = password

        self.mark_dirty(game)
        return game

    def getContainer(self, name):
        if name in self._containers:
            return self._containers[name]
        return None

    @property
    def active_games(self):
        games = []
        for c, g in self._containers.items():
            games += g.games
        return games

    def remove_game(self, game: Game):
        for c, g in self._containers.items():
            if game in g.games:
                g.games.remove(game)

    def all_game_modes(self):
        modes = []
        for c, g in self._containers.items():
            modes.append({
                'command': 'mod_info',
                'name': g.game_mode,
                'fullname': g.gameNiceName,
                'icon': None,
                'host': g.host,
                'join': g.join,
                'live': g.live,
                'desc': g.desc,
                'options': []
            })
        return modes

    def find_by_id(self, id: int):
        """
        Look up a game by ID
        :rtype: Game
        """
        for container in self._containers:
            game = self._containers[container].findGameByUuid(id)
            if game is not None:
                return game
