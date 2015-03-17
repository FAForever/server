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

RANKS = {0:["Private", "Corporal", "Sergeant", "Captain", "Major", "Colonel", "General", "Supreme Commander"],
         1:["Paladin", "Legate", "Priest", "Centurion", "Crusader", "Evaluator", "Avatar-of-War", "Champion"],
         2:["Drone", "Node", "Ensign", "Agent", "Inspector", "Starshina", "Commandarm" ,"Elite Commander"],
         3:["Su", "Sou", "Soth", "Ithem", "YthiIs", "Ythilsthe", "YthiThuum", "Suythel Cosethuum"]
         }

FACTIONS = {0:"UEF", 1:"Aeon",2:"Cybran",3:"Seraphim"}

from collections import deque
import random


class NewsFeed(object):
    def __init__(self, parent = None):
        self.parent = parent
        self.news = deque(maxlen=20)
        
    def addNews(self, news):
        self.news.append(news)
        self.spreadNews()
    
    def getNews(self):
        news = []
        for new in self.news :
            news.append(new)
        return news
    
    def spreadNews(self):
        self.parent.sendNews()
        
    def rankingUp(self, uid, faction):
        between = ["has been promoted to", "is now a", "rank is now", "has ranked up to"]
        rank, name = self.parent.findPlayerInfos(uid)
        self.addNews("%s %s %s" % (name, random.choice(between), RANKS[faction][rank]))
        
    def domination(self, winner, loser):
        factionWin = FACTIONS[winner]
        factionLose = FACTIONS[loser]
        self.addNews("!!! %s are dominated by %s !!! They are now under their control !" % (factionLose, factionWin))
        
    def playerDeath(self, uid, faction, faction_murderer, planetuid):
        rank, name = self.parent.findPlayerInfos(uid)
        planet = self.parent.planets[planetuid]
        planetname = planet["name"]
        
        rankname = RANKS[faction][rank]
        faction = FACTIONS[faction_murderer]
        self.addNews("%s %s has been killed by %s on %s" % (rankname, name, faction, planetname))
    
    def newPlayer(self, uid, faction):
        _, name = self.parent.findPlayerInfos(uid)
        self.addNews("%s has joined the %s army" % (name, FACTIONS[faction]))
        
    def planetFlipped(self, planetuid, faction):
        planet = self.parent.planets[planetuid]
        self.addNews("%s is now in %s hands" % (planet["name"], FACTIONS[faction]))