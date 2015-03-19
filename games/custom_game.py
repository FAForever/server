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

from .game import Game

logger = logging.getLogger(__name__)


class CustomGame(Game):
    def __init__(self, uuid, parent = None):
        super(self.__class__, self).__init__(uuid, parent)
  
    def specialInit(self, player):
        trueskill = player.getRating()
        trueSkillCopy = deepcopy(trueskill)
        self.addTrueSkillPlayer(trueSkillCopy)

    def specialEnding(self, logger, db, players):
        timeLimit = len(self.trueSkillPlayers) * 60
        if time.time() - self.createDate < timeLimit:
            self.setInvalid("Score are invalid: Play time was not long enough (under %i seconds)" % timeLimit)
            logger.debug("Game is invalid: Play time was not long enough (under %i seconds)" % timeLimit)
        if self.isValid():
            tsresults = self.computeResults()
            tsplayers = self.trueSkillPlayers
            self.trueSkillUpdate(tsresults, tsplayers, logger, db, players, sendScore = False)
