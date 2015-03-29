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

from copy import deepcopy
import time
import logging
from src.abc.base_game import InitMode

from .game import Game


logger = logging.getLogger(__name__)

FACTIONS = {1:"UEF", 2:"Aeon",3:"Cybran",4:"Seraphim"}

class matchmakerGame(Game):
    """Class for matchmaker game"""
    init_mode = InitMode.AUTO_LOBBY

    def __init__(self, uuid, parent = None):
        super(self.__class__, self).__init__(uuid, parent)
        
        self.playerToJoin = [] 
        self.minPlayer = 2

        self.team1 = []
        self.team2 = []

    def addPlayerToJoin(self, player):
        if not player in self.playerToJoin : 
            self.playerToJoin.append(player)

    def getPlayerToJoin(self):
        return self.playerToJoin


    def specialInit(self, player):
        pass

    def specialEnding(self, logger, db, players):
        pass
