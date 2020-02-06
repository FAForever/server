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


def make_matches(searches: List[Search]) -> List[Match]:
    return Matchmaker(searches).find()


@with_logger
class MatchmakingPolicy(object):
    def __init__(self, searches: List[Search]):
        self.searches = searches
        self.matches: Dict[Search, Search] = {}

    def _match(self, s1: Search, s2: Search):
        self._logger.debug(f"Matching %s and %s ({self.__class__})", s1, s2)
        self.matches[s1] = s2
        self.matches[s2] = s1

    def _unmatch(self, s1: Search):
        s2 = self.matches[s1]
        self._logger.debug(f"Unmatching %s and %s ({self.__class__})", s1, s2)
        assert self.matches[s2] == s1
        del self.matches[s1]
        del self.matches[s2]


class StableMarriage(MatchmakingPolicy):
    def find(self) -> Dict[Search, Search]:
        """Perform SM_NUM_TO_RANK runs of the stable matching algorithm.
        Assumes that _MatchingGraph.build_sparse() only returns edges whose matches are acceptable
        to both parties."""
        ranks = _MatchingGraph.build_sparse(self.searches)
        self.matches.clear()

        for i in range(SM_NUM_TO_RANK):
            self._logger.debug(
                "Round %i of stable marriage, currently %i matches", i,
                len(self.matches) // 2
            )
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
                    search, preferred,
                    search.quality_with(preferred),
                    search.match_threshold,
                    preferred.match_threshold
                )

                self._propose(search, preferred)

        self._register_unmatched_searches()

        return self.matches

    def _register_unmatched_searches(self):
        """
        Tells all unmatched searches that they went through a failed matching
        attempt.
        """
        unmatched_searches = filter(
            lambda search: search not in self.matches,
            self.searches
        )
        for search in unmatched_searches:
            search.register_failed_matching_attempt()
            self._logger.debug(
                "Search %s remained unmatched at threshold %f in attempt number %i",
                search, search.match_threshold, search.failed_matching_attempts
            )

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


class RandomlyMatchNewbies(MatchmakingPolicy):
    def find(self) -> Dict[Search, Search]:
        self.matches.clear()

        unmatched_newbies = [
            search for search in self.searches
            if search.is_single_ladder_newbie() and search not in self.matches
        ]

        while len(unmatched_newbies) >= 2:
            newbie1 = unmatched_newbies.pop()
            newbie2 = unmatched_newbies.pop()
            self._match(newbie1, newbie2)

        if len(unmatched_newbies) == 1:
            newbie = unmatched_newbies[0]

            default_if_no_available_opponent = None

            opponent = next((
                search for search in self.searches
                if search != newbie and search not in self.matches
                and search.is_single_party() and search.has_no_top_player()
            ), default_if_no_available_opponent)
            if opponent is not default_if_no_available_opponent:
                self._match(newbie, opponent)

        return self.matches


@with_logger
class Matchmaker(object):
    def __init__(self, searches: List[Search]):
        self.searches = searches
        self.matches: Dict[Search, Search] = {}

    def find(self) -> List[Match]:
        self._logger.debug("Matching with stable marriage...")
        self.matches.update(StableMarriage(self.searches).find())

        remaining_searches = [
            search for search in self.searches if search not in self.matches
        ]
        self._logger.debug("Matching randomly for remaining newbies...")
        self.matches.update(RandomlyMatchNewbies(remaining_searches).find())

        return self._remove_duplicates()

    def _remove_duplicates(self) -> List[Match]:
        matches_set: Set[Match] = set()
        for s1, s2 in self.matches.items():
            if (s1, s2) in matches_set or (s2, s1) in matches_set:
                continue
            matches_set.add((s1, s2))
        return list(matches_set)


@with_logger
class _MatchingGraph:
    def __init__(self):
        self.quality = Cache(Search.quality_with)

    @staticmethod
    def build_sparse(searches: List[Search]) -> Dict[Search, List[Search]]:
        """ A graph in adjacency list representation, whose nodes are the searches
        and whose edges are the top few possible matchings for each node.

        Note that the highest quality searches come at the end of the list so that
        it can be used as a stack with .pop().
        """
        graph = _MatchingGraph()
        return {
            search: sorted(
                graph._get_top_matches(
                    search, filter(lambda s: s is not search, searches)
                ),
                key=lambda other: graph.quality(search, other)
            )
            for search in searches
        }

    def _get_top_matches(self, search: Search, others: Iterable[Search]) -> List[Search]:
        def is_possible_match(other: Search) -> bool:
            log_string = "Quality between %s and %s: %s thresholds: [%s, %s]."
            log_args = (
                search, other, self.quality(search, other),
                search.match_threshold, other.match_threshold
            )

            quality = self.quality(search, other)
            if search._match_quality_acceptable(other, quality):
                _MatchingGraph._logger.debug(
                    f"{log_string} Will be considered during stable marriage.",
                    *log_args
                )
                return True
            else:
                _MatchingGraph._logger.debug(
                    f"{log_string} Will be discarded for stable marriage.",
                    *log_args
                )
                return False

        return heapq.nlargest(
            SM_NUM_TO_RANK,
            filter(is_possible_match, others),
            key=lambda other: self.quality(search, other)
        )


# Performance helpers

class Cache(object):
    def __init__(self, func):
        self.func = func
        self.data = {}

    def __call__(self, *args):
        if args in self.data:
            return self.data[args]
        else:
            res = self.func(*args)
            self.data[args] = res
            return res
