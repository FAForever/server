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

import game
gameClass = reload(game)
from game import Game

from copy import deepcopy
import time
import logging

logger = logging.getLogger(__name__)

FACTIONS = {1:"UEF", 2:"Aeon",3:"Cybran",4:"Seraphim"}

class matchmakerGame(Game):
    '''Class for matchmaker game'''

    def __init__(self, uuid, parent = None):
        super(self.__class__, self).__init__(uuid, parent)
        
        self.playerToJoin = [] 
        self.minPlayer = 2

        self.initMode = 1
        
        self.team1 = []
        self.team2 = []

    def specialInit(self, player):          
        #print "custom special init"
        trueskill = player.getRating()
        trueSkillCopy = deepcopy(trueskill)
        self.addTrueSkillPlayer(trueSkillCopy)
        #print "custom special init done"

    def addPlayerToJoin(self, player):
        if not player in self.playerToJoin : 
            self.playerToJoin.append(player)

    def getPlayerToJoin(self):
        return self.playerToJoin


    def specialInit(self, player):          
        try :
            self.log.debug("player " + str(player.getLogin()))
            #print "custom special init"
            trueskill = player.getRating()
            trueSkillCopy = deepcopy(trueskill)
            self.addTrueSkillPlayer(trueSkillCopy)
            
            if player.getAction() == "HOST" :
                
                place = self.getPositionOfPlayer(player.getLogin())  
                self.setPlayerFaction(place, player.getFaction())
                self.setPlayerColor(place, place)

                playerToJoin = self.getPlayerToJoin()
                mapname = str(self.getMapName())
                team = 1
                for p in playerToJoin :
                    place = self.getPositionOfPlayer(p.getLogin())  
                    if p in self.team1 :
                        team = 2
                        
                    elif p in self.team2:
                        team = 3

                    else:
                        self.log.debug("player " + str(p.getLogin()) + " not a team")

                    self.setPlayerFaction(place, p.getFaction())
                    self.setPlayerColor(place, place)
                    
                    p.setWantGame(True)

                    json = {}
                    json["command"] = "game_launch"
                    json["mod"] = self.parent.gameTypeName
                    json["reason"] = "ranked"
                    json["uid"] = self.uuid
                    json["mapname"] = mapname
    
                    self.log.debug("Host is %s" % player.getLogin() )
                    self.log.debug("launching FA for %s, place %i" % (p.getLogin(),place) )
                    
                       
                    json["args"] = ["/players %i" % self.numPlayers, "/team %i" % team, "/StartSpot %i" % place, "/%s" % FACTIONS[p.getFaction()]]
                    p.getLobbyThread().sendJSON(json)
                    
              
            
        except :
            self.log.exception("Something awful happened when launching a matchmaker game !")





        
    def specialEnding(self, logger, db, players):
        
        timeLimit = len(self.trueSkillPlayers) * 60
        
        if time.time() - self.createDate < timeLimit :
            self.setInvalid("Score are invalid : Play time was not long enough (under %i seconds)" % timeLimit)
            logger.debug("Game is invalid : Play time was not long enough (under %i seconds)" % timeLimit)
        if self.isValid() :
            tsresults = self.computeResults()
            tsplayers = self.getTrueSkillPlayers()
            self.trueSkillUpdate(tsresults, tsplayers, logger, db, players, sendScore = False)
#        else :
#            tsplayers = self.getTrueSkillPlayers()
#            for playerTS in tsplayers : 
#                name = playerTS.getPlayer()
#                self.sendMessageToPlayers(players, name, self.getInvalidReason())
