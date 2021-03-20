import itertools
import random
from collections import OrderedDict
from typing import (
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar
)

from ...decorators import with_logger
from ..search import CombinedSearch, Match, Search
from .stable_marriage import Matchmaker, StableMarriageMatchmaker, avg_mean

T = TypeVar("T")
Buckets = Dict[Search, List[Tuple[Search, float]]]


@with_logger
class BucketTeamMatchmaker(Matchmaker):
    """
    Uses heuristics to group searches of any size
    into CombinedSearches of team_size
    and then runs StableMarriageMatchmaker
    to produce a list of matches from these.
    """

    def find(self, searches: Iterable[Search]) -> List[Match]:
        teams = self._find_teams(searches)
        matchmaker1v1 = StableMarriageMatchmaker(1)
        return matchmaker1v1.find(teams)

    def _find_teams(self, searches: Iterable[Search]) -> List[Search]:
        full_teams = []
        unmatched = searches
        need_team = []
        for search in unmatched:
            if len(search.players) == self.team_size:
                full_teams.append(search)
            else:
                need_team.append(search)

        if all(len(s.players) == 1 for s in need_team):
            teams, unmatched = _make_teams_from_single(need_team, self.team_size)
        else:
            teams, unmatched = _make_teams(need_team, self.team_size)
        full_teams.extend(teams)

        return full_teams


def _make_teams_from_single(
    searches: List[Search], size: int
) -> Tuple[List[Search], List[Search]]:
    """
    Make teams in the special case where all players are solo queued (no
    parties).

    Tries to put players of similar skill on the same team as long as there are
    enough such players to form at least 2 teams. If there are not enough
    similar players for two teams, then distributes similarly rated players
    accross different teams.

    # Algorithm
    1. Group players into "buckets" by rating. This is a sort of heuristic for
        determining which players have similar rating.
    2. Create as many games as possible within each bucket.
    3. Create games from remaining players by balancing teams with players from
        different buckets.
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
            selected = remaining[: 2 * size]
            new_searches.extend(_distribute(selected, size))
        else:
            selected = remaining[:size]
            new_searches.append(CombinedSearch(*[s for s, m in selected]))

        remaining = [item for item in remaining if item not in selected]

    return new_searches, [search for search, _ in remaining]


def _make_buckets(searches: List[Search]) -> Buckets:
    """
    Group players together by similar rating.

    # Algorithm
    1. Choose a random player as the "pivot".
    2. Find all players with rating within 100 pts of this player and place
        them in a bucket.
    3. Repeat with remaining players.
    """
    remaining = list(map(lambda s: (s, avg_mean(s)), searches))
    buckets: Buckets = {}

    while remaining:
        # Choose a pivot
        pivot, mean = random.choice(remaining)
        low, high = mean - 100, mean + 100

        # Partition remaining based on how close their means are
        bucket, not_bucket = [], []
        for item in remaining:
            (_, other_mean) = item
            if low <= other_mean <= high:
                bucket.append(item)
            else:
                not_bucket.append(item)

        buckets[pivot] = bucket
        remaining = not_bucket

    return buckets


def _distribute(
    items: List[Tuple[Search, float]], team_size: int
) -> Iterator[CombinedSearch]:
    """
    Distributes a sorted list into teams of a given size in a balanced manner.
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
    rotated = items[:half] + rotate(items[half:], half // 2)
    for i, (search, _) in enumerate(rotated):
        # Distribute the pairs to the appropriate team
        teams[i % num_teams].append(search)

    return (CombinedSearch(*team) for team in teams)


def _make_teams(searches: List[Search], size: int) -> Tuple[List[Search], List[Search]]:
    """
    Tries to group as many searches together into teams of the given size as
    possible. Returns the new grouped searches, and the remaining searches that
    were not succesfully grouped.

    Does not try to balance teams so it should be used only as a last resort.
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
    """
    Creates a lookup table indexed by number of players in the search.
    """

    searches_by_size: Dict[int, Set[Search]] = OrderedDict()

    # Would be easier with defaultdict, but we want to preserve key order
    for search in searches:
        size = len(search.players)
        if size not in searches_by_size:
            searches_by_size[size] = set()
        searches_by_size[size].add(search)

    return searches_by_size


def _make_team_for_search(
    search: Search, searches_by_size: Dict[int, Set[Search]], size: int
) -> Optional[Search]:
    """
    Match this search with other searches to create a new team of `size`
    members.
    """

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


def _uncombine(search: Search, searches_by_size: Dict[int, Set[Search]]) -> None:
    """
    Adds all of the searches in search back to their respective spots in
    `searches_by_size`.
    """

    if not isinstance(search, CombinedSearch):
        searches_by_size[len(search.players)].add(search)
        return

    for s in search.searches:
        _uncombine(s, searches_by_size)


def rotate(list_: List[T], amount: int) -> List[T]:
    return list_[amount:] + list_[:amount]
