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

import bisect

class replayArmyContainer(object):
    def __init__(self):
        self.__armies = []
        self.__armyId = {}
        
    def __iter__(self) :
        for pair in iter(self.__armies) :
            yield pair[1]
    
    def __len__(self) :
        return len(self.__armies)
    
    def clear(self):
        self.__armies = []
        
    def add(self, army):
        if id(army) in self.__armyId :
            return False
        key = self.key(army.id)
        bisect.insort_left(self.__armies, [key, army])
        self.__armyId[id(army)] = army
        return True
    
    def key(self, id):
        return id