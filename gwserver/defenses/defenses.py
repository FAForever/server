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

class item(object):
    def __init__(self, itemuid, parent=None):
        self.uid = itemuid
        self.amount = 0
        self.description = ""
        self.structure = ""
        
    def update(self, amount, description, structure):
        self.amount = amount
        self.description = description
        self.structure = structure

class defense(object):
    def __init__(self, planet, parent=None):
        self.parent = parent
        self.planet = planet
        
        self.defenses = {}

    def hasDefense(self, itemuid):
        if itemuid in self.defenses:
            return True
        return False

    def addDefense(self, itemuid, amount, description, structure):
        if self.hasDefense(itemuid) is False and amount != 0:
            self.defenses[itemuid] = item(itemuid, self)
        
        if self.hasDefense(itemuid) is True :
            self.defenses[itemuid].update(amount, description, structure)
            
    def getDefenses(self, check):
        items = []
        for item in self.defenses:
            amount = self.defenses[item].amount
            if amount == 0 and check is True:
                continue             
            items.append(dict(command="planet_defense_info", planetuid=self.planet, amount=self.defenses[item].amount, itemuid=self.defenses[item].uid, description=self.defenses[item].description, structure=self.defenses[item].structure))
        return items

class Defenses(object):
    def __init__(self, parent = None):
        self.parent = parent
        self.defenses = {}
        
    def update(self):
        self.defenses = {}
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT planetuid, itemuid, amount, description, structure FROM planets_defense LEFT JOIN static_defenses ON static_defenses.id=planets_defense.itemuid WHERE amount != 0")
        if not query.exec_():
            self.log.warning(query.lastError())
        if query.size() > 0 :
            #query.first()
            while query.next() :                
                planetuid   = int(query.value(0))
                itemuid     = int(query.value(1))
                amount      = int(query.value(2))
                description = str(query.value(3))
                structure   = str(query.value(4))
                
                if not planetuid in self.defenses:
                    self.defenses[planetuid] = defense(planetuid, self.parent)
                self.defenses[planetuid].addDefense(itemuid, amount, description, structure)
       
          
    def planetHasDefense(self, planetuid):
        if planetuid in self.defenses:
            return True
        return False
    
    def getDefenses(self, planetuid, check=False):
        if self.planetHasDefense(planetuid):
            return self.defenses[planetuid].getDefenses(check)   
        return []
            