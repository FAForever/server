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


class Teams(object):
    """ Teams object"""
    
    def __init__(self, parent = None):
        self.parent = parent
        self.teams = {}
        
    def addInSquad(self, leader, teammate):
        """ create a squad, check if the teamate is not already in one squad"""
        for squad in self.teams:
            if squad == teammate:
                return False
            if teammate in self.teams[squad]:
                return False
            
        if not leader in self.teams:
            self.teams[leader] = []
    
        self.teams[leader].append(teammate)
        return True
    
    def removeFromSquad(self, squad, uid):
        if squad in self.teams:
            if uid in self.teams[squad]:
                self.teams[squad].remove(uid)
                 
    def disbandSquad(self, squad):
        if squad in self.teams:
            del self.teams[squad]
        
    
    def getSquadLeader(self, uid):
        for squad in self.teams:
            if squad == uid:
                return squad
            if uid in self.teams[squad]:
                return squad
        return None  
    
    def getAllMembers(self, uid):
        members = []
        if uid in self.teams:
            if not uid in members:
                members.append(uid)
            
            for tuid in self.teams[uid]:
                if not tuid in members:
                    members.append(tuid)
        return members                

    def isInSquad(self, uid):
        """ Check if a player is in a squad already"""
        for squad in self.teams:
            if squad == uid:
                return True
            if uid in self.teams[squad]:
                return True
        return False  
    
    def isLeader(self, uid):
        """ check if the player is a leader"""
        for squad in self.teams:
            if squad == uid:
                return True
        return False              
