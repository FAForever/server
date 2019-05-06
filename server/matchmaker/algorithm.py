import heapq
from collections import deque
from statistics import mean
from typing import Deque, Dict, Iterable, List

from .search import Search

################################################################################
#                           Constants and parameters                           #
################################################################################

# The maximum amount of time (in seconds) to wait if no one is searching.
MAX_QUEUE_POP_TIME = 60 * 15
# An arbitrary number determining how rapidly the queue time falls off when the
# number of players increases. See https://www.desmos.com/calculator/v3tdrjbqub.
QUEUE_POP_TIME_SCALE_FACTOR = 20
# How many previous queue sizes to consider
QUEUE_TIME_MOVING_AVG_SIZE = 5

# Number of candidates for matching
SM_NUM_TO_RANK = 5

last_queue_amounts: Deque[int] = deque()


def time_until_next_pop(num_queued: int) -> int:
    """ Calculate how long we should wait for the next queue to pop based
    on a moving average of the amount of people in the queue.

    Uses a simple inverse relationship. See

    https://www.desmos.com/calculator/v3tdrjbqub

    for an exploration of possible functions.
    """
    last_queue_amounts.append(num_queued)
    if len(last_queue_amounts) > QUEUE_TIME_MOVING_AVG_SIZE:
        last_queue_amounts.popleft()

    x = mean(last_queue_amounts)
    # Essentially y = max_time / (x+1) with a scale factor
    return int(MAX_QUEUE_POP_TIME / (x / QUEUE_POP_TIME_SCALE_FACTOR + 1))


def stable_marriage(searches: List[Search]):
    ranks = rank_all(searches)
    matches: Dict[Search, Search] = {}

    for i in range(SM_NUM_TO_RANK):
        # Do one round of proposals
        for search in searches:
            if search in matches:
                continue
            try:
                preferred = ranks[search].pop()
            except IndexError:
                # Unable to find any matches for this search
                del ranks[search]
                continue
            except KeyError:
                # Unable to find any matches for this search
                continue
            if not search.matches_with(preferred):
                continue

            # search 'proposes' to preferred #

            # If preferred does not have a match, then match them
            if preferred not in matches:
                match(matches, search, preferred)
                continue

            current_match = matches[preferred]
            current_quality = preferred.quality_with(current_match)
            new_quality = search.quality_with(preferred)

            if new_quality > current_quality:
                # Found a better match
                unmatch(matches, preferred)
                match(matches, search, preferred)

    matches_set = set()
    for s1, s2 in matches.items():
        if (s1, s2) in matches_set or (s2, s1) in matches_set:
            continue
        matches_set.add((s1, s2))
    return list(matches_set)


def match(matches: Dict[Search, Search], s1: Search, s2: Search):
    matches[s1] = s2
    matches[s2] = s1


def unmatch(matches: Dict[Search, Search], s1: Search):
    s2 = matches[s1]
    assert matches[s2] == s1
    del matches[s1]
    del matches[s2]


def rank_all(searches: List[Search]) -> Dict[Search, List[Search]]:
    """ Returns searches with best quality for each search.

    Note that the highest quality searches come at the end of the list so that
    it can be used as a stack with .pop().
    """
    return {
        search: sorted(filter(
            lambda s: s is not search,
            rank_partners(search, searches)
        ), key=lambda other: search.quality_with(other))
        for search in searches
    }


def rank_partners(search: Search, others: Iterable[Search]) -> List[Search]:
    return heapq.nlargest(SM_NUM_TO_RANK, others, key=lambda other: search.quality_with(other))
