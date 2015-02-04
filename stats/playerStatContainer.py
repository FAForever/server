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

from .xmlParser import *
import bisect

class playerStatContainer(object):
    def __init__(self) :
        self.__playerStats = []
        self.__playerId = {}
    
    def __iter__(self) :
        for pair in iter(self.__playerStats) :
            yield pair[1]
    
    def __len__(self) :
        return len(self.__playerStats)
    
    def clear(self):
        self.__playerStats = []
        
    def add(self, playerStat):
        if id(playerStat) in self.__playerId :
            return False
        key = self.key(playerStat.playerId)
        bisect.insort_left(self.__playerStats, [key, playerStat])
        self.__playerId[id(playerStat)] = playerStat
        return True
    
    def key(self, id):
        return id
    
    def importSax(self, stats):
        handler = SaxStatsHandler(self)
        parser = QXmlSimpleReader()
        parser.setContentHandler(handler)
        parser.setErrorHandler(handler)
        datas = QXmlInputSource()
        datas.setData(stats)
        return parser.parse(datas)
        
    