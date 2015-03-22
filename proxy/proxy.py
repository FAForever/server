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
from proxy.couple import couple


class proxy(object):
    def __init__(self):

        self.proxies = {}
        
        for i in range(11):
            self.proxies[i] = []
        
        self.couples = []
        

    def coupleExists(self, player1, player2):    
        """ check if that couple already exists"""
        for c in self.couples :
            if c.isCouple(player1, player2):
                return True
        
        return False
                    
    def findFreeProxyPort(self, couple):
        """ this function return a free proxy number for both player"""
        
        player1Free = []
        player2Free = []
        
        for proxy in self.proxies :
            if not couple.player1 in self.proxies[proxy]:
                player1Free.append(proxy)
            if not couple.player2 in self.proxies[proxy]:
                player2Free.append(proxy)
        
        common = set(player1Free) & set(player2Free)
        if len(common) > 0 :
            return list(common)[0]

        return -1


    def addCouple(self, player1, player2):
        """ this function add two players that are supposed to connect through proxy"""
        
        # first check if that couple doesn't exist yet.
        if not self.coupleExists(player1, player2):
            c = couple(player1, player2)
            
            
            freePort = self.findFreeProxyPort(c)

            if freePort != -1 :
                self.proxies[freePort].append(player1)
                self.proxies[freePort].append(player2)
                c.setProxy(freePort)
                
            
            self.couples.append(c)
            

    def findProxy(self, player1, player2):
        for couple in self.couples :
            if couple.isCouple(player1, player2):
                return couple.port
            
        return None
                
    def removePlayer(self, player):
        cleaned = False
        # first clearing the proxies
        for proxy in self.proxies :
            if player in self.proxies[proxy]:
                self.proxies[proxy].remove(player)  
                cleaned = True  
        
        # and the couples
        
        for c in reversed(self.couples):
            if c.contains(player):
                self.couples.remove(c)
                cleaned = True
                
        return cleaned
