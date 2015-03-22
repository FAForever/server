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

class replayArmy(object):

    def __init__(self):

        self.color = 0
        self.civilian = False
        self.faction = 1
        self.id = ''
        self.team = 0
        self.human = True
        


    def populate(self, infos):
        armyInfo = dict(infos)
        self.color = armyInfo['PlayerColor']
        self.civilian = armyInfo['Civilian']
        self.faction = armyInfo['Faction']
        self.id = armyInfo['PlayerName']
        self.team = armyInfo['Team']
        self.human = armyInfo['Human']

        
        
    def isPlayer(self):
        return not self.civilian and self.human
        
    def __str__(self):
        return "%s : team (%i)" % (self.id, self.team)