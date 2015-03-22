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

class couple(object):
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.port = None


    def isCouple(self, player1, player2):
        return (self.player1 == player1 and self.player2 == player2) \
               or (self.player2 == player1 and self.player1 == player2)


    def setProxy(self, port):
        self.port = port


    def contains(self, player):
        if self.player1 == player or self.player2 == player:
            return True
        return False


    def __repr__(self):
        if self.port is not None:
            return "found free port %i for %s and %s" % (self.port, self.player1, self.player2)
        else:
            return "No free port for %s and %s" % (self.player1, self.player2)