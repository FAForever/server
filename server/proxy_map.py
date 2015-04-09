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

        if players not in self._map:
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
