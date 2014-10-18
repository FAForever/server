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

class Army(object):
    def __init__(self, id=None, type=None, built=0, lost=0, killed=0) :
        self.id = id
        self.built = built
        self.lost= lost
        self.killed = killed
        self.type = type

    def getBuilt(self):
        return self.built

    def getLost(self):
        return self.lost
    
    def getKilled(self):
        return self.killed

    def getId(self):
        return self.id
    
    def getType(self):
        return self.type
    
    def __str__(self):
        return "%s (%s) : Built : %i, Lost : %i, killed : %i" % (self.id, self.type, self.built, self.lost, self.killed)