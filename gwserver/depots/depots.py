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


from PySide.QtSql import QSqlQuery
import time


class Depot():
    def __init__(self, uid, influence, reinforcement, money, parent = None):
        self.uid = uid
        self.influence = influence
        self.money = money
        self.reinforcement = reinforcement

    def getDepotStats(self):
   
        return dict(command="planet_depot_info", planetuid=self.uid, influence = self.influence, money=self.money, reinforcement=self.reinforcement)

class Depots(object):
    def __init__(self, parent = None):
        self.parent = parent
        self.depots = {}
    
    
    def update(self):
        '''Updating depots'''

        self.depots = {}
        
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT planetuid, influence, reinforcements, money FROM `planets_depots`  WHERE 1")
        query.exec_()
        if query.size() > 0 :
            while query.next():
                uid             = int(query.value(0))        
                influence       = int(query.value(1))
                reinforcements  = int(query.value(2))
                money           = int(query.value(3))
                
                if not uid in self.depots:
                    self.depots[uid] = Depot(uid, influence, reinforcements, money, self)

    def planetHasDepot(self, planetuid):
        if planetuid in self.depots:
            return True
        return False
    
    def getDepot(self, planetuid):
        if self.planetHasDepot(planetuid):
            return self.depots[planetuid].getDepotStats()
        return None