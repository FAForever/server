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

import random, math
from ladder.ladderMaps import ladderMaps
from PySide import QtSql
from PySide import QtCore

from PySide.QtSql import *
import re
import operator

class swisstournament(object):
    def __init__(self, id, name = None, host = None, minPlayers = 2, maxPlayers = 99, minrating = 0, maxrating = 9000, description = "", date = "", parent = None):
        
        self.uuid = id
        
        self.type = "swissTourney"
        self.parent = parent
        self.name = name
        self.host = host.getLogin()
        self.players = []
        self.seededplayers = []
        self.minPlayers = minPlayers
        self.maxPlayers = maxPlayers
        
        self.minRating = minrating
        self.maxRating = maxrating
        self.description = description
        
        self.date = date
        
        self.state = "open"
        self.rounds = 1
        self.curRound = 1
        self.addRound = 0
        self.round = {}
        
        
    def getName(self):
        return self.name
        
    def getid(self):
        return self.uuid
        
    def getState(self):
        return self.state
    
    def getplayersNames(self):
        return self.players
            
    def countRounds(self):
        if len(self.players) > 0 :
            self.rounds = int(math.ceil(math.log(len(self.players), 2))) + self.addRound

            
        
    
    def addPlayer(self, player):
        if len(self.players) > self.maxPlayers :
            return False
        
        if not player in self.players :
            self.players.append(player)
            self.countRounds()
            return True
        return False
    
    def removePlayer(self, player):
        if player in self.players :
            self.players.remove(player)
            self.countRounds()
            return True
        return False
    
    def round_even(self):
        return round(len(self.players)/2.)*2
    
    def getRoundsNumber(self):
        self.rounds + self.addRound
        return self.rounds

    def chunks2(self, l, n):

        chunks = [l[i:i+n] for i in range(0, len(l), n)]
        for i in range(len(chunks)) :
            if len(chunks[i]) == 1 :
                chunks.remove(chunks[i])
        return chunks

    def chunks(self, l, n):
        return [l[max(0,len(l)+i-n):len(l)+i] for i in range(0, -len(l), -n)]



    def getCurrentRound(self):
        return self.curRound
    
    def advanceRound(self):
        
        if self.curRound == self.countRounds() :
            return False
        
        for i in  self.round[self.curRound] :
            if not "result" in  self.round[self.curRound][i] :
                return False
        
        self.curRound = self.curRound + 1
        return True 
        

    def registerScore(self, player, result):

        if player in self.players :

            if self.round[self.curRound][player]["against"] != -1:

                    otherplayer = self.round[self.curRound][player]["against"]
                    
                    otherresult = 0
                    if result == 1 :
                        otherresult = 0
                    elif result == 0 :
                        otherresult = 1
                    elif result == 0.5 :
                        otherresult = .5
                    
                    
                    self.round[self.curRound][otherplayer]["result"] = otherresult
                    self.round[self.curRound][player]["result"] = result

                    for p in self.seededplayers :
                        if p["name"] == player :
                            p["score"] =  p["score"] + result
                        elif p["name"] == otherplayer :
                            p["score"] = p["score"] + otherresult

    def savePairing(self, r, matchups):
        thisround = {}

        for player in self.players :
            normalPairing = [item[1] for item in matchups if player is item[0]] or [item[0] for item in matchups if player is item[1]]
            thisround[player] = {}
            if len(normalPairing) > 0 :
                thisround[player]["against"] = normalPairing[0]
            else :
                thisround[player]["against"] = -1
                thisround[player]["result"] = 1
                for p in self.seededplayers :
                    if p["name"] == player :
                        
                        p["score"] =  (p["score"]) + 0
                
        self.round[r] = thisround


    def getScores(self):
        scores = {}
        for player in self.players :
            score = 0
            for r in self.round :
                if "result" in self.round[r][player] :
                    score = score + self.round[r][player]["result"]
            
            scores[player] = score
        return scores


    def swapPairing(self, pairing, player, previousSwap):

        a = pairing.index(player)

        if a < len(pairing)-1 :
            b = a + 1
            pairing[b], pairing[a] = pairing[a], pairing[b]
        else :
            
            b = a - 1
            while pairing[b] == previousSwap :
                b = b - 1
              
            pairing[b], pairing[a] = pairing[a], pairing[b]
            
        return pairing[b]

    def doSeeding(self):
        self.seededplayers = []
        for i in range(0, len(self.players)) :
            seeded = {}
            seeded["name"] = self.players[i]
            seeded["seed"] = i
            seeded["score"] = 0
            self.seededplayers.append(seeded) 
        
        

    def doPairing(self):
        if self.curRound == 1 :
            if len(self.players) >= 2 :
                self.doSeeding()
                
                listSorted = sorted(self.seededplayers, key=lambda elem: "%i %i" % (elem['score'], len(self.seededplayers)-elem['seed']), reverse=True)
                
                pairings = []
                
                for val in listSorted :
                    pairings.append(val["name"])
                #listSorted = ['test1', 'test2', 'test3', 'test4', 'test5', 'test6']
                chunks = self.chunks(pairings, int(self.round_even() / 2))
                

                self.savePairing(self.curRound, list(zip(chunks[0], chunks[1])) )
            
        else :
            #winners are matched against winners, losers against losers
            scores = self.getScores()
            
            listSorted = sorted(self.seededplayers, key=lambda elem: "%f %i" % (elem['score'], len(self.seededplayers)-elem['seed']), reverse=True)

            pairings = []
            for val in listSorted :
                pairings.append(val["name"])
            
            
            chunks = self.chunks2(pairings, 2)

            iteration = 0
            swapped = None
            while True :
                iteration = iteration + 1
                listChanged = False
                
                
                
                for player in pairings:
                    normalPairing = [item[1] for item in chunks if player is item[0]] or [item[0] for item in chunks if player is item[1]]
                    
                    if len(normalPairing) == 0 :
                        normalPairing = -1
                    else :
                        normalPairing = normalPairing[0]

                    #check if that user was already matched against that player.
                    for r in self.round :
                        if normalPairing == self.round[r][player]["against"] :
                            swapped = self.swapPairing(pairings, player, swapped)
                            chunks = self.chunks2(pairings, 2)
                            listChanged = True
                           
                if iteration == 40 :
                    print("too many errors")
                    break
                if listChanged == False  :
                    break
            
            
            self.savePairing(self.curRound, chunks )


    def getPairing(self, r):
        if r <= self.curRound :
            return self.round[r]          
        
    def getDisplayInfos(self):
        if self.state == "open" :
            self.doPairing()
        infos = {}
        infos["rounds"] = self.getRoundsNumber()
        infos["players"] = self.players
        infos["current_rounds"] = self.getCurrentRound()
        infos["pairings"] = self.round
        return infos


class swissTourneyContainerClass(gamesContainerClass):
    '''Class for swiss tournament games'''
    
    def __init__(self, db, parent = None):
        super(swissTourneyContainerClass, self).__init__("swissTourney", "Swiss-type tournament" ,db, parent)
        
        self.type = 1
        self.listable = False
        self.host = False
        self.join = False
        self.parent = parent

        self.tourney = []

    def getTournaments(self):
        return self.tourney

    def createTourney(self, name, player, minPlayers, maxPlayers, minRating, maxRating, description, date):
        

        query = QtSql.QSqlQuery(self.db)
        query.prepare("INSERT INTO swiss_tournaments (`host`, `name`, `description`, `minplayers`, `maxplayers`, `minrating`, `maxrating`, `tourney_state`, `tourney_date`) VALUE ( ?, ?, ? ,? , ?, ?, ? ,0, ?)")
        query.addBindValue(player.getId())
        query.addBindValue(name)
        query.addBindValue(description)
        query.addBindValue(minPlayers)
        query.addBindValue(maxPlayers)
        query.addBindValue(minRating)
        query.addBindValue(maxRating)
        query.addBindValue(date)
        query.exec_() 
        uuid = query.lastInsertId()

        
        tourney = swisstournament(uuid, name, player, minPlayers, maxPlayers, minRating, maxRating, description, date, self)
        self.tourney.append(tourney)

        for p in self.parent.players.getAllPlayers() :

            jsonToSend = {}
            jsonToSend["command"] = "tournament_info"
            jsonToSend["type"] = tourney.type
            jsonToSend["state"] = tourney.getState()
            jsonToSend["uid"] = tourney.getid()
            jsonToSend["title"] = tourney.getName()
            jsonToSend["host"] = player.getLogin()
            jsonToSend["min_players"] = tourney.minPlayers
            jsonToSend["max_players"] = tourney.maxPlayers
            jsonToSend["min_rating"] = tourney.minRating
            jsonToSend["max_rating"] = tourney.maxRating
            jsonToSend["description"] = tourney.description
            jsonToSend["players"] = tourney.getplayersNames()
            jsonToSend["date"] = tourney.date
            

            p.getLobbyThread().sendJSON(jsonToSend)

    
    def removeTourny(self, tourney):
        if tourney in self.tourney :
            self.tourney.remove(tourney)
            
