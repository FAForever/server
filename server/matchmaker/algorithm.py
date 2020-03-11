import itertools
import math
import random
from collections import OrderedDict
from statistics import mean
from typing import (
    Dict, Iterable, Iterator, List, Optional, Set, Tuple, TypeVar
)

from ..decorators import with_logger
from .search import CombinedSearch, Match, Search

T = TypeVar("T")
WeightedGraph = Dict[Search, List[Tuple[Search, float]]]
Buckets = Dict[Search, List[Tuple[Search, float]]]


def make_matches(searches: Iterable[Search]) -> List[Match]:
    """
    Main entrypoint for the matchmaker algorithm.
    """
    return Matchmaker(searches).find()


@with_logger
class MatchmakingPolicy(object):
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


class StableMarriage(MatchmakingPolicy):
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


class RandomlyMatchNewbies(MatchmakingPolicy):
    def find(self, searches: Iterable[Search]) -> Dict[Search, Search]:
        self.matches.clear()

        unmatched_newbies = [
            search for search in searches
            if search.is_single_ladder_newbie()
        ]

        while len(unmatched_newbies) >= 2:
            newbie1 = unmatched_newbies.pop()
            newbie2 = unmatched_newbies.pop()
            self._match(newbie1, newbie2)

        if len(unmatched_newbies) == 1:
            newbie = unmatched_newbies[0]

            default_if_no_available_opponent = None

            opponent = next((
                search for search in searches
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
                "Search %s remained unmatched at threshold %f in attempt number %i",
                search, search.match_threshold, search.failed_matching_attempts
            )

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
        for search, neighbors in list(graph.items()):
            if not neighbors:
                del graph[search]


def avg_mean(search: Search) -> float:
    """ Get the average of all trueskill means for a search counting means with
    high deviation as 0. """
    return mean(map(
        lambda r: r[0] if r[1] < 250 else 0,
        search.ratings
    ))


def rotate(l: List[T], amount: int) -> List[T]:
    return l[amount:] + l[:amount]


def make_teams_from_single(
    searches: List[Search],
    size: int
) -> Tuple[List[Search], List[Search]]:
    """
    Make teams in the special case where all players are solo queued (no
    parties).

    Tries to put players of similar skill on the same team as long as there are
    enough such players to form at least 2 teams. If there are not enough enough
    similar players for two teams, then distributes similarly rated players
    accross different teams.
    """
    assert all(len(s.players) == 1 for s in searches)

    # Make buckets
    buckets = _make_buckets(searches)
    remaining: List[Tuple[Search, float]] = []

    new_searches: List[Search] = []
    # Match up players within buckets
    for bucket in buckets.values():
        # Always produce an even number of teams
        num_groups = len(bucket) // (size * 2)
        num_teams = num_groups * 2
        num_players = num_teams * size

        selected = random.sample(bucket, num_players)
        # TODO: Optimize?
        remaining.extend(s for s in bucket if s not in selected)
        # Sort by trueskill mean
        selected.sort(key=lambda item: item[1])
        new_searches.extend(_distribute(selected, size))

    # Match up players accross buckets
    remaining.sort(key=lambda item: item[1])
    while len(remaining) >= size:
        if len(remaining) >= 2 * size:
            # enough for at least 2 teams
            selected = remaining[:2 * size]
            new_searches.extend(_distribute(selected, size))
        else:
            selected = remaining[:size]
            new_searches.append(CombinedSearch(*[s for s, m in selected]))

        remaining = [item for item in remaining if item not in selected]

    return new_searches, [search for search, _ in remaining]


def _make_buckets(searches: List[Search]) -> Buckets:
    remaining = list(map(lambda s: (s, avg_mean(s)), searches))
    buckets: Buckets = {}

    while remaining:
        # Choose a pivot
        pivot, mean = random.choice(remaining)
        low, high = mean - 50, mean + 50

        # Partition remaining based on how close their means are
        bucket, not_bucket = [], []
        for item in remaining:
            (_, other_mean) = item
            if other_mean >= low and other_mean <= high:
                bucket.append(item)
            else:
                not_bucket.append(item)

        buckets[pivot] = bucket
        remaining = not_bucket

    return buckets


def _distribute(
    items: List[Tuple[Search, float]],
    team_size: int
) -> Iterator[CombinedSearch]:
    """
    Distributes a sorted list into teams of a given size in a ballanced manner.
    Player "skill" is determined by their position in the list.

    For example (using numbers to represent list positions)
    ```
    _distribute([1,2,3,4], 2) == [[1,4], [2,3]]
    ```
    In this simple scenario, one team gets the best and the worst player and
    the other player gets the two in the middle. This is the only way of
    distributing these 4 items into 2 teams such that there is no obviously
    favored team.
    """
    num_teams = len(items) // team_size
    teams: List[List[Search]] = [[] for _ in range(num_teams)]
    half = len(items) // 2
    # Rotate the second half of the list
    rotated = items[:half] + rotate(items[half:], half // 2 - 1)
    for i, (search, _) in enumerate(rotated):
        # Distribute the pairs to the appropriate team
        teams[i % num_teams].append(search)

    return (CombinedSearch(*team) for team in teams)


def make_teams(
    searches: List[Search],
    size: int
) -> Tuple[List[Search], List[Search]]:
    """ Tries to group as many searches together into teams of the given size as
    possible. Returns the new grouped searches, and the remaining searches that
    were not succesfully grouped.
    """

    searches_by_size = _make_searches_by_size(searches)

    new_searches = []
    for search in searches:
        if len(search.players) > size:
            continue

        new_search = _make_team_for_search(search, searches_by_size, size)
        if new_search:
            new_searches.append(new_search)

    return new_searches, list(itertools.chain(*searches_by_size.values()))


def _make_searches_by_size(searches: List[Search]) -> Dict[int, Set[Search]]:
    """ Creates a lookup table indexed by number of players in the search """

    searches_by_size: Dict[int, Set[Search]] = OrderedDict()

    # Would be easier with defaultdict, but we want to preserve key order
    for search in searches:
        size = len(search.players)
        if size not in searches_by_size:
            searches_by_size[size] = set()
        searches_by_size[size].add(search)

    return searches_by_size


def _make_team_for_search(
    search: Search, searches_by_size: Dict[int, Set[Search]], size
) -> Optional[Search]:
    """ Match this search with other searches to create a new team of `size`
    members. """

    num_players = len(search.players)
    if search not in searches_by_size[num_players]:
        return None
    searches_by_size[num_players].remove(search)

    if num_players == size:
        return search

    num_needed = size - num_players
    try_size = num_needed
    new_search = search
    while num_needed > 0:
        if try_size == 0:
            _uncombine(new_search, searches_by_size)
            return None

        try:
            other = searches_by_size[try_size].pop()
            new_search = CombinedSearch(new_search, other)
            num_needed -= try_size
            try_size = num_needed
        except KeyError:
            try_size -= 1

    return new_search


def _uncombine(
    search: Search, searches_by_size: Dict[int, Set[Search]]
):
    """ Adds all of the searches in search back to their respective spots in
    `searches_by_size`. """

    if not isinstance(search, CombinedSearch):
        searches_by_size[len(search.players)].add(search)
        return

    for s in search.searches:
        _uncombine(s, searches_by_size)
