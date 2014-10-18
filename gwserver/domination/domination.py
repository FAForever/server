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
class Domination(object):
    
    def __init__(self, parent = None):
        self.parent = parent
        self.dominations = {}
        
        self.getCurrentDomination()
        
    def getCurrentDomination(self):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT dominant, slave FROM `domination` WHERE 1")
        query.exec_()
        if query.size() > 0:
            query.first()
            dominant = int(query.value(0))
            slave = int(query.value(1))
            if not slave in self.dominations:
                self.dominations[slave] = dominant
                
    def getSlaves(self):
        return self.dominations.keys()
    
    def getDominants(self):
        return self.dominations.values()
    
    def getDominantSlaves(self, dominant):
        slaves = []
        for slave in self.dominations:
            if self.dominations[slave] == dominant:
                slaves.append(slave)
        return slaves
                
             
    def add(self, winner, loser):
        query = QSqlQuery(self.parent.db)
        query.prepare("INSERT INTO `domination`(`dominant`, `slave`) VALUES (?,?)")
        query.addBindValue(winner)
        query.addBindValue(loser)
        query.exec_()        


        query.prepare("UPDATE `domination` SET `dominant`=? WHERE dominant = ?")
        query.addBindValue(winner)
        query.addBindValue(loser)
        query.exec_()        

        self.dominations[loser] = winner    
            
    def isDominated(self, faction):
        if faction in self.dominations:
            return True
        return False
    
    def getDominant(self, faction):
        if faction in self.dominations:
            return self.dominations[faction]
        return None