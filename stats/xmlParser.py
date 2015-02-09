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

from PySide.QtGui import *
from PySide.QtXml import *

from .armyContainer import *
from .army import *
from .playerStat import *

#def fltFromQStr(qstr):
#    """
#    A function to change a QString into a float
#  
#    :param qstr: a QString
#    :type qstr: PyQt4.QtCore.QString
#    :return: the value of the QString
#    :rtype: float
#    """
#    i, ok = qstr.toFloat()
#    if ok:
#        return i
#    else:
#        return qstr
#def intFromQStr(qstr):
#    """
#    A function to change a QString into a int
#  
#    :param qstr: a QString
#    :type qstr: PyQt4.QtCore.QString
#    :return: the value of the QString
#    :rtype: int
#    """
#    i, ok = qstr.toInt()
#    if ok:
#        return i
#    else:
#        return qstr

class SaxStatsHandler(QXmlDefaultHandler) :
    def __init__(self, playersStats):
        super(SaxStatsHandler, self).__init__()
        
        self.playerStats = playersStats
        
        self.text = ""
        self.player = None
        self.listUnits = ArmyContainer()
        self.id = None
  
        
    def clear(self):
        #print "cleared"
        self.player = None
        self.id = None
        self.listUnits = ArmyContainer()
        
        self.mass = []
        self.energy = []
        
    def startElement(self, namespaceURI, localName, qName, attributes):
        #print qName
        if qName == "Army" :
            armyName = attributes.value('name')
            index = int(attributes.value('index'))
            
            
            self.id = index
            self.player = armyName

        if qName == "Unit" :
            
            id = attributes.value('id')
            type = attributes.value('type')
            built =  int(attributes.value('built'))
            lost = int(attributes.value('lost'))
            killed = int(attributes.value('killed'))
            
            self.listUnits.add(Army(id, type, built, lost, killed))

        if qName == "Mass" :
            produced = float(attributes.value("produced"))
            consumed = float(attributes.value("consumed"))
            self.mass = [produced, consumed]  

        if qName == "Energy" :
            produced = float(attributes.value("produced"))
            consumed = float(attributes.value("consumed"))
            self.energy = [produced, consumed] 
        
        return True
    
    def endElement(self,namespaceURI,localName,qName): 
        if qName == "Army" :
            if self.player.lower() != "civilian" :
                self.playerStats.add(playerStat(str(self.player), self.id, self.listUnits, self.mass, self.energy ))
#
            self.clear()

            
        
        return True
        

    def characters(self, text):
        #print "character: " + text
        return True
    
    def error(self,exception):
        print("Exception",exception.message())
        return

