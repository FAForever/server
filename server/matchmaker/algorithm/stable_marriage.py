import itertools
import math
import random
import statistics as stats
from collections import OrderedDict
from typing import (
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)

from ...decorators import with_logger
from ..search import CombinedSearch, Match, Search

WeightedGraph = Dict[Search, List[Tuple[Search, float]]]



@with_logger
class MatchmakingPolicy1v1(object):
    def __init__(self):
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


class StableMarriage(MatchmakingPolicy1v1):
    def find(self, ranks: WeightedGraph) -> Dict[Search, Search]:
        """ Perform the stable matching algorithm until a maximal stable matching
        is found.
        """
        self.matches.clear()

        max_degree = max((len(edges) for edges in ranks.values()), default=0)
        for i in range(max_degree):
            self._logger.debug(
                "Round %i of stable marriage, currently %i matches", i,
                len(self.matches) // 2
            )
            # Do one round of proposals
            if len(self.matches) == len(ranks):
                # Everyone found a match so we are done
                break

            for search in ranks:
                if search in self.matches:
                    continue

                if not ranks[search]:
                    # Preference list exhausted
                    continue

                preferred, quality = ranks[search].pop()

                self._logger.debug(
                    "Quality between %s and %s: %f thresholds: [%f, %f]",
                    search, preferred, quality,
                    search.match_threshold,
                    preferred.match_threshold
                )

                self._propose(search, preferred, quality)

        return self.matches

    def _propose(self, search: Search, preferred: Search, new_quality: float):
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

        if new_quality > current_quality:
            # Found a better match
            self._unmatch(preferred)
            self._match(search, preferred)


class RandomlyMatchNewbies(MatchmakingPolicy1v1):
    def find(self, searches: Iterable[Search]) -> Dict[Search, Search]:
        self.matches.clear()

        unmatched_newbies = []
        first_opponent = None
        for search in searches:
            if search.has_top_player():
                continue

            if search.has_newbie():
                unmatched_newbies.append(search)
            elif not first_opponent and search.failed_matching_attempts >= 1:
                first_opponent = search

        while len(unmatched_newbies) >= 2:
            newbie1 = unmatched_newbies.pop()
            newbie2 = unmatched_newbies.pop()
            self._match(newbie1, newbie2)

        if unmatched_newbies and first_opponent:
            newbie = unmatched_newbies[0]
            self._match(newbie, first_opponent)

        return self.matches

@with_logger
class Matchmaker(object):
    def __init__(self, searches: Iterable[Search], team_size: int):
        self.searches = searches
        self.matches: Dict[Search, Search] = {}
        self.team_size = team_size

    def _register_unmatched_searches(self):
        """
        Tells all unmatched searches that they went through a failed matching
        attempt.
        """
        for search in self.searches:
            if search in self.matches:
                continue

            search.register_failed_matching_attempt()
            self._logger.debug(
                "Search %s remained unmatched at threshold %f in attempt number %s",
                search, search.match_threshold, search.failed_matching_attempts
            )



@with_logger
class StableMarriageMatchmaker(Matchmaker):
    def __init__(self, searches: Iterable[Search], team_size: int):
        super().__init__(searches, team_size)
        if team_size != 1:
            self._logger.error(
                "Invalid team size %i for stable marriage matchmaker will be ignored",
                team_size
            )

    def find(self) -> List[Match]:
        self._logger.debug("Matching with stable marriage...")
        searches = list(self.searches)
        if len(searches) < 30:
            ranks = _MatchingGraph.build_full(searches)
        else:
            ranks = _MatchingGraph.build_fast(searches)
        _MatchingGraph.remove_isolated(ranks)
        self.matches.update(StableMarriage().find(ranks))

        remaining_searches = [
            search for search in self.searches if search not in self.matches
        ]
        self._logger.debug("Matching randomly for remaining newbies...")
        self.matches.update(RandomlyMatchNewbies().find(remaining_searches))

        self._register_unmatched_searches()

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
    @staticmethod
    def build_full(searches: List[Search]) -> WeightedGraph:
        """ A graph in adjacency list representation, whose nodes are the searches
        and whose edges are the possible matchings for each node. Checks every
        possible edge for inclusion in the graph.

        Note that the highest quality searches come at the end of the list so that
        it can be used as a stack with .pop().

        Time complexity: O(n^2)
        """
        adj_list = {search: [] for search in searches}

        # Generate every edge. There are 'len(searches) choose 2' of these.
        for search, other in itertools.combinations(searches, 2):
            quality = search.quality_with(other)
            if not _MatchingGraph.is_possible_match(search, other, quality):
                continue

            # Add the edge in both directions
            adj_list[search].append((other, quality))
            adj_list[other].append((search, quality))

        # Sort edges by their weights i.e. match quality
        for search, neighbors in adj_list.items():
            neighbors.sort(key=lambda edge: edge[1])

        return adj_list

    @staticmethod
    def build_fast(searches: List[Search]) -> WeightedGraph:
        """ Builds approximately the same graph as `build_full`, but does not
        check every possible edge.

        Time complexity: O(n*log(n))
        """
        adj_list = {search: [] for search in searches}
        # Sort all searches by players average trueskill mean
        searches = sorted(searches, key=avg_mean)
        # Now compute quality with `num_to_check` nearby searches on either side
        num_to_check = int(math.log(max(16, len(searches)), 2)) // 2
        for i, search in enumerate(searches):
            for other in searches[i+1:i+1+num_to_check]:
                quality = search.quality_with(other)
                if not _MatchingGraph.is_possible_match(search, other, quality):
                    continue

                # Add the edge in both directions
                adj_list[search].append((other, quality))
                adj_list[other].append((search, quality))

        # Sort edges by their weights i.e. match quality
        for search, neighbors in adj_list.items():
            neighbors.sort(key=lambda edge: edge[1])

        return adj_list

    @staticmethod
    def is_possible_match(search: Search, other: Search, quality: float) -> bool:
        log_string = "Quality between %s and %s: %.3f thresholds: [%.3f, %.3f]."
        log_args = (
            search, other, quality,
            search.match_threshold, other.match_threshold
        )

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

    @staticmethod
    def remove_isolated(graph: WeightedGraph):
        """ Remove any searches that have no possible matchings.

        Note: This assumes that edges are undirected. Calling this on directed
        graphs will produce incorrect results. """
        for search, neighbors in list(graph.items()):
            if not neighbors:
                del graph[search]

def avg_mean(search: Search) -> float:
    """
    Get the average of all trueskill means for a search counting means with
    high deviation as 0.
    """
    return stats.mean(mean if dev < 250 else 0 for mean, dev in search.ratings)

