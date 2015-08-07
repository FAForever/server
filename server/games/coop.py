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
from server.abc.base_game import InitMode
from . import GamesContainer
from .game import Game

class CoopGame(Game):
    """Class forcoop game"""

    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, uuid, parent = None):
        super(self.__class__, self).__init__(uuid, parent)



class CoopGamesContainer(GamesContainer):
    """Class for coop games"""
    listable = False

    def __init__(self, db, games_service=None, name='coop', nice_name='coop'):
        super(CoopGamesContainer, self).__init__(name, nice_name, db, games_service)

        self.host = False
        self.join = False
