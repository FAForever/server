import heapq
from typing import Dict, Iterable, List, Set

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


def stable_marriage(searches: List[Search]) -> List[Match]:
    return StableMarriage(searches).find()


@with_logger
class StableMarriage(object):
    def __init__(self, searches: List[Search]):
        self.searches = searches

    def find(self) -> List[Match]:
        """Perform SM_NUM_TO_RANK runs of the stable matching algorithm. 
        Assumes that _MatchingGraph.build_sparse() only returns edges whose matches are acceptable
        to both parties."""
        ranks = _MatchingGraph.build_sparse(self.searches)
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

                self._propose(search, preferred)

        self._forcefully_match_unmatched_newbies()

        return self._remove_duplicates()

    def _forcefully_match_unmatched_newbies(self):
        unmatched_newbies = [
            search for search in self.searches 
            if search.is_single_ladder_newbie()
            and not search in self.matches
        ] 

        while len(unmatched_newbies) >= 2:
            newbie1 = unmatched_newbies.pop()
            newbie2 = unmatched_newbies.pop()
            self._match(newbie1, newbie2)

        if len(unmatched_newbies) == 1:
            newbie = unmatched_newbies[0]

            default_if_no_available_opponent = None

            opponent = next(
                (search for search in self.searches
                if search != newbie
                and not search in self.matches
                and search.is_single_party()
                and search.has_no_top_player()
                ),
                default_if_no_available_opponent
            )
            if opponent is not default_if_no_available_opponent:
                self._match(newbie, opponent)


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


@with_logger
class _MatchingGraph:
    @staticmethod
    def build_sparse(searches: List[Search]) -> Dict[Search, List[Search]]:
        """ A graph in adjacency list representation, whose nodes are the searches
        and whose edges are the top few possible matchings for each node.

        Note that the highest quality searches come at the end of the list so that
        it can be used as a stack with .pop().
        """
        return {
            search: sorted(
                _MatchingGraph._get_top_matches(
                    search, filter(lambda s: s is not search, searches)
                ),
                key=lambda other: search.quality_with(other)
            )
            for search in searches
        }


    @staticmethod
    def _get_top_matches(search: Search, others: Iterable[Search]) -> List[Search]:
        def is_possible_match(other: Search) -> bool:
            quality_log_string = (
                f"Quality between {search} and {other}: {search.quality_with(other)}"
                + f" thresholds: [{search.match_threshold}, {other.match_threshold}]."
            )

            if search.matches_with(other):
                _MatchingGraph._logger.debug(
                    quality_log_string + f" Will be considered during matchmaking."
                )
                return True
            else:
                _MatchingGraph._logger.debug(
                    quality_log_string + f" Will be discarded."
                )
                return False

        return heapq.nlargest(
            SM_NUM_TO_RANK, 
            filter(
                is_possible_match,
                others
            ), 
            key=lambda other: search.quality_with(other)
        )
