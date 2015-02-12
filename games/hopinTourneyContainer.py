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

from .gamesContainer import  gamesContainerClass
from trueSkill.TrueSkill.FactorGraphTrueSkillCalculator import * 
from trueSkill.Team import *
from trueSkill.Teams import *
from .ladderGame import ladder1V1Game

import random
from PySide import QtSql
from PySide import QtCore

from PySide.QtSql import *
import re
import math

class tournament(object):
    def __init__(self, id, name = None, host = None, minPlayers = 2, maxPlayers = 10, parent = None):
        
        self.uuid = id
        self.parent = parent
        self.name = name
        self.host = host
        self.players = []
        self.minPlayers = minPlayers
        self.maxPlayers = maxPlayers
        self.state = "open"
        self
        
        
    def getName(self):
        return self.name
        
    def getid(self):
        return self.uuid
        
    def getState(self):
        return self.state
    
    def addPlayer(self, player):
        if not player in self.players :
            self.players.append(player)
            return True
        return False
    
    def removePlayer(self, player):
        if player in self.players :
            self.players.remove(player)
            return True
        return False


class hopinTourneyContainerClass(gamesContainerClass):
    '''Class for 1vs1 ladder games'''
    
    def __init__(self, db, parent = None):
        super(hopinTourneyContainerClass, self).__init__("hopintourneysingleelimination", "Hop-in Single Elimination" ,db, parent)
        
        self.players = []
        self.type = 1
        self.listable = False
        self.host = False
        self.join = False
        self.parent = parent
        self.mod = "faf"
        
        self.tourney = []

    def getTournaments(self):
        return self.tourney

    def createTourney(self, name, player, minPlayers, maxPlayers):
        
        print("we do this")
        query = QtSql.QSqlQuery(self.db)
        queryStr = ("INSERT INTO hopin_tournament (`host`) VALUE ( %i )" % player.getId())
        query.exec_(queryStr)      
        uuid = query.lastInsertId()
        uuid = 1
        
        tourney = tournament(uuid, name, player, minPlayers, maxPlayers, self)
        self.tourney.append(tourney)

        jsonToSend = {}
        jsonToSend["command"] = "social"
        jsonToSend["autojoin"] = re.sub(r'\W+', '_', name)
        player.getLobbyThread().sendJSON(jsonToSend)

        for p in self.parent.players.getAllPlayers() :
            print(p)
            jsonToSend = {}
            jsonToSend["command"] = "tournament_info"
            jsonToSend["state"] = tourney.getState()
            jsonToSend["uid"] = tourney.getid()
            jsonToSend["title"] = tourney.getName()
            jsonToSend["host"] = player.getLogin()
            jsonToSend["min_players"] = tourney.minPlayers
            jsonToSend["max_players"] = tourney.maxPlayers
            print(jsonToSend)
            p.getLobbyThread().sendJSON(jsonToSend)

    
    def removeTourny(self, tourney):
        if tourney in self.tourney :
            self.tourney.remove(tourney)