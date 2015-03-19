from abc import ABCMeta, abstractproperty

from trueskill import Rating


class BasePlayer():
    """
    Abstract base class for players
    """
    __metaclass__ = ABCMeta

    def __init__(self):
        self._global_rating = (None, None)
        self._ladder_rating = (None, None)

    @property
    def global_rating(self):
        return Rating(*self._global_rating)

    @global_rating.setter
    def global_rating(self, value: Rating):
        self._global_rating = (value.mu, value.sigma)

    @property
    def ladder_rating(self):
        return Rating(*self._ladder_rating)

    @ladder_rating.setter
    def ladder_rating(self, value: Rating):
        self._ladder_rating = (value.mu, value.sigma)

    login = abstractproperty()
