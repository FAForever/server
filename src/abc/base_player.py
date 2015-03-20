from abc import ABCMeta, abstractproperty

from trueskill import Rating

from src.abc.faction import Faction


class BasePlayer():
    """
    Abstract base class for players
    """
    __metaclass__ = ABCMeta

    def __init__(self):
        self._faction = 0
        self._global_rating = (None, None)
        self._ladder_rating = (None, None)

    @property
    def global_rating(self):
        return Rating(*self._global_rating)

    @global_rating.setter
    def global_rating(self, value: Rating):
        if isinstance(value, Rating):
            self._global_rating = (value.mu, value.sigma)
        else:
            self._global_rating = value

    @property
    def ladder_rating(self):
        return Rating(*self._ladder_rating)

    @ladder_rating.setter
    def ladder_rating(self, value: Rating):
        if isinstance(value, Rating):
            self._ladder_rating = (value.mu, value.sigma)
        else:
            self._ladder_rating = value

    login = abstractproperty()
    id = abstractproperty()

    @property
    def faction(self):
        return self._faction

    @faction.setter
    def faction(self, value):
        if isinstance(value, str):
            self._faction = Faction.from_string(value)
        else:
            self._faction = value
