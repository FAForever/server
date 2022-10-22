from abc import ABC, abstractmethod
from typing import Iterable

from ...decorators import with_logger
from ..search import Match, Search


@with_logger
class Matchmaker(ABC):
    @abstractmethod
    def find(
        self,
        searches: Iterable[Search],
        team_size: int,
        rating_peak: float
    ) -> tuple[list[Match], list[Search]]:
        pass


@with_logger
class MatchmakingPolicy1v1(object):
    def __init__(self):
        self.matches: dict[Search, Search] = {}
        self.searches_remaining_unmatched: set[Search] = set()

    def _match(self, s1: Search, s2: Search):
        self._logger.debug(
            "Matching %s and %s (%s)",
            s1, s2, self.__class__
        )
        self.matches[s1] = s2
        self.matches[s2] = s1
        self.searches_remaining_unmatched.discard(s1)
        self.searches_remaining_unmatched.discard(s2)

    def _unmatch(self, s1: Search):
        s2 = self.matches[s1]
        self._logger.debug(
            "Unmatching %s and %s (%s)",
            s1, s2, self.__class__
        )
        assert self.matches[s2] == s1
        del self.matches[s1]
        del self.matches[s2]
        self.searches_remaining_unmatched.add(s1)
        self.searches_remaining_unmatched.add(s2)
