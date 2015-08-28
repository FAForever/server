from abc import ABCMeta

from trueskill import Rating

from faf.faction import Faction


class BasePlayer:
    """
    Abstract base class for players
    """
    __metaclass__ = ABCMeta

    def __init__(self, id, login):
        self._faction = 0
        self._global_rating = (1500, 500)
        self._ladder_rating = (1500, 500)

        self.id = id
        self.login = login

    @property
    def global_rating(self):
        return self._global_rating

    @global_rating.setter
    def global_rating(self, value: Rating):
        if isinstance(value, Rating):
            self._global_rating = (value.mu, value.sigma)
        else:
            self._global_rating = value

    @property
    def ladder_rating(self):
        return self._ladder_rating

    @ladder_rating.setter
    def ladder_rating(self, value: Rating):
        if isinstance(value, Rating):
            self._ladder_rating = (value.mu, value.sigma)
        else:
            self._ladder_rating = value

    @property
    def faction(self):
        return self._faction

    @faction.setter
    def faction(self, value):
        if isinstance(value, str):
            self._faction = Faction.from_string(value)
        else:
            self._faction = value
