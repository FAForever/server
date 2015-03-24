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


class ProxyMap():
    """
    Used for determining which local proxy ports to use for connecting players
    """
    max_port = 11

    def __init__(self):
        self._map = {}

    def find_free_port(self, pair: frozenset):
        """
        Given a pair of players, find a port unused by either
        :param pair:
        :return:
        """
        mapped_ports = [port
                        for players, port
                        in self._map.items() if len(pair.intersection(players)) > 0]
        for i in range(ProxyMap.max_port):
            if i not in mapped_ports:
                return i
        return -1

    def __contains__(self, item):
        """
        Given either a tuple of players or a single player,
        test whether there is a mapping for them
        :param item:
        :return:
        """
        if not isinstance(item, tuple):
            item = (item,)
        for players in self._map.keys():
            if len(players.intersection(item)) > 0:
                return True
        return False

    def map(self, *players):
        """
        Find a free proxy number and mark the given pair of players as connected by it
        :param players: A pair of players
        :return:
        """
        players = frozenset(players)
        assert len(players) == 2

        if players not in self._map.keys():
            self._map[players] = self.find_free_port(players)

        return self._map[players]

    def unmap(self, player):
        """
        Unmap a given player
        :param player:
        :return:
        """
        cleaned = False
        keys = list(self._map.keys())
        for c in keys:
            if player in c:
                del self._map[c]
                cleaned = True
                
        return cleaned
