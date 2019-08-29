import heapq
from collections import deque
from typing import Deque, Dict, Iterable, List, Set

from ..decorators import with_logger
from .search import Match, Search

################################################################################
#                           Constants and parameters                           #
################################################################################

# Number of candidates for matching
SM_NUM_TO_RANK = 5

################################################################################
#                                Implementation                                #
################################################################################

last_queue_amounts: Deque[int] = deque()


def stable_marriage(searches: List[Search]) -> List[Match]:
    return StableMarriage(searches).find()


@with_logger
class StableMarriage(object):
    def __init__(self, searches: List[Search]):
        self.searches = searches

    def find(self) -> List[Match]:
        "Perform stable matching"
        ranks = _rank_all(self.searches)
        self.matches: Dict[Search, Search] = {}

        for i in range(SM_NUM_TO_RANK):
            self._logger.debug("Round %i currently %i matches", i, len(self.matches) // 2)
            # Do one round of proposals
            if len(self.matches) == len(self.searches):
                # Everyone found a match so we are done
                break

            for search in self.searches:
                if search in self.matches:
                    continue

                if not ranks[search]:
                    # Preference list exhausted
                    continue

                preferred = ranks[search].pop()

                self._logger.debug(
                    "Quality between %s and %s: %f thresholds: [%f, %f]",
                    search, preferred, search.quality_with(preferred),
                    search.match_threshold, preferred.match_threshold
                )
                if not search.matches_with(preferred):
                    continue

                self._propose(search, preferred)

        return self._remove_duplicates()

    def _remove_duplicates(self) -> List[Match]:
        matches_set: Set[Match] = set()
        for s1, s2 in self.matches.items():
            if (s1, s2) in matches_set or (s2, s1) in matches_set:
                continue
            matches_set.add((s1, s2))
        return list(matches_set)

    def _propose(self, search: Search, preferred: Search):
        """ An unmatched search proposes to it's preferred opponent.

        If the opponent is not matched, they become matched. If the opponent is
        matched, but prefers this new search to its current one, then the opponent
        unmatches from its previous adversary and matches with the new search instead.
        """
        if preferred not in self.matches:
            self._match(search, preferred)
            return

        current_match = self.matches[preferred]
        current_quality = preferred.quality_with(current_match)
        new_quality = search.quality_with(preferred)

        if new_quality > current_quality:
            # Found a better match
            self._unmatch(preferred)
            self._match(search, preferred)

    def _match(self, s1: Search, s2: Search):
        self._logger.debug("Matching %s and %s", s1, s2)
        self.matches[s1] = s2
        self.matches[s2] = s1

    def _unmatch(self, s1: Search):
        s2 = self.matches[s1]
        self._logger.debug("Unmatching %s and %s", s1, s2)
        assert self.matches[s2] == s1
        del self.matches[s1]
        del self.matches[s2]


def _rank_all(searches: List[Search]) -> Dict[Search, List[Search]]:
    """ Returns searches with best quality for each search.

    Note that the highest quality searches come at the end of the list so that
    it can be used as a stack with .pop().
    """
    return {
        search: sorted(
            _rank_partners(
                search, filter(lambda s: s is not search, searches)
            ),
            key=lambda other: search.quality_with(other)
        )
        for search in searches
    }


def _rank_partners(search: Search, others: Iterable[Search]) -> List[Search]:
    matchable_others = [other for other in others if search.matches_with(other)]
    return heapq.nlargest(SM_NUM_TO_RANK, matchable_others, key=lambda other: search.quality_with(other))
