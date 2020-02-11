from typing import Dict, Iterable, List, Set, Tuple

from ..decorators import with_logger
from .search import Match, Search

WeightedGraph = Dict[Search, List[Tuple[Search, float]]]


def make_matches(searches: Iterable[Search]) -> List[Match]:
    return Matchmaker(searches).find()


@with_logger
class MatchmakingPolicy(object):
    def __init__(self, searches: Iterable[Search]):
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
        """ Perform the stable matching algorithm until a maximal stable matching
        is found. Assumes that _MatchingGraph.build_weighted() only returns edges
        whose matches are acceptable to both parties.
        """
        ranks = _MatchingGraph.build_weighted(self.searches)
        _MatchingGraph.remove_isolated(ranks)
        max_degree = max((len(edges) for edges in ranks.values()), default=0)

        self.matches.clear()

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
    def __init__(self, searches: Iterable[Search]):
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
    @staticmethod
    def build_weighted(searches: Iterable[Search]) -> WeightedGraph:
        """ A graph in adjacency list representation, whose nodes are the searches
        and whose edges are the possible matchings for each node.

        Note that the highest quality searches come at the end of the list so that
        it can be used as a stack with .pop().
        """
        adj_list = {search: [] for search in searches}

        # Generate every edge. There are 'len(searches) choose 2' of these.
        searches = [s for s in searches if s is not None]
        for search, other in subset_pairs(searches):
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

    def is_possible_match(search: Search, other: Search, quality: float) -> bool:
        log_string = "Quality between %s and %s: %s thresholds: [%s, %s]."
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
        for k, v in list(graph.items()):
            if not v:
                del graph[k]


def subset_pairs(l: list):
    """ Generates all possible 2 subsets of `l` as tuples. Each pair of items will
    show up in only one order and the elements in the pair will be distinct.
    Note that the number of items generated is `len(l) choose 2`.

    # Example

    subset_pairs([1, 2, 3]) yields pairs (1, 2), (1, 3), (2, 3)

    Note that this has O(n^2) time complexity.
    """
    for i, a in enumerate(l[:-1]):
        for b in l[i+1:]:
            yield a, b
