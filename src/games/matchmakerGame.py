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

from src.games.game import Game


logger = logging.getLogger(__name__)

FACTIONS = {1:"UEF", 2:"Aeon",3:"Cybran",4:"Seraphim"}

class matchmakerGame(Game):
    """Class for matchmaker game"""

    def __init__(self, uuid, parent = None):
        super(self.__class__, self).__init__(uuid, parent)
        
        self.playerToJoin = [] 
        self.minPlayer = 2

        self.initMode = 1
        
        self.team1 = []
        self.team2 = []

    def addPlayerToJoin(self, player):
        if not player in self.playerToJoin : 
            self.playerToJoin.append(player)

    def getPlayerToJoin(self):
        return self.playerToJoin


    def specialInit(self, player):          
        try :
            self._logger.debug("player " + str(player.getLogin()))
            #print "custom special init"
            trueskill = player.getRating()
            trueSkillCopy = deepcopy(trueskill)
            self.addTrueSkillPlayer(trueSkillCopy)
            
            if player.getAction() == "HOST" :
                
                place = self.getPositionOfPlayer(player.getLogin())  
                self.setPlayerFaction(place, player.getFaction())
                self.setPlayerColor(place, place)

                playerToJoin = self.getPlayerToJoin()
                mapname = self.mapName
                team = 1
                for p in playerToJoin :
                    place = self.getPositionOfPlayer(p.getLogin())  
                    if p in self.team1 :
                        team = 2
                        
                    elif p in self.team2:
                        team = 3

                    else:
                        self._logger.debug("player " + str(p.getLogin()) + " not a team")

                    self.setPlayerFaction(place, p.getFaction())
                    self.setPlayerColor(place, place)
                    
                    p.wantToConnectToGame = True

                    json = {
                        "command": "game_launch",
                        "mod": self.parent.gameTypeName,
                        "reason": "ranked",
                        "uid": self.uuid,
                        "mapname": mapname,
                        "args": [
                            "/players %i" % self.numPlayers,
                            "/team %i" % team,
                            "/StartSpot %i" % place,
                            "/%s" % FACTIONS[p.getFaction()]
                        ]
                    }

                    self._logger.debug("Host is %s" % player.getLogin() )
                    self._logger.debug("launching FA for %s, place %i" % (p.getLogin(),place) )

                    p.lobbyThread.sendJSON(json)
        except :
            self._logger.exception("Something awful happened when launching a matchmaker game !")

    def specialEnding(self, logger, db, players):
        
        timeLimit = len(self.trueSkillPlayers) * 60
        
        if time.time() - self.createDate < timeLimit :
            self.setInvalid("Score are invalid : Play time was not long enough (under %i seconds)" % timeLimit)
            logger.debug("Game is invalid : Play time was not long enough (under %i seconds)" % timeLimit)
        if self.isValid() :
            tsresults = self.compute_rating()
            tsplayers = self.trueSkillPlayers
            self.trueSkillUpdate(tsresults, tsplayers, logger, db, players, sendScore = False)
