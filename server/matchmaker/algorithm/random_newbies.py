from typing import Iterable

from ..search import Match, Search
from .matchmaker import MatchmakingPolicy1v1


class RandomlyMatchNewbies(MatchmakingPolicy1v1):
    def find(
        self, searches: Iterable[Search]
    ) -> tuple[dict[Search, Search], list[Match]]:
        self.matches.clear()
        searches_remaining_unmatched = set(searches)

        unmatched_newbies: list[Search] = []
        first_opponent = None
        for search in searches:
            if search.has_high_rated_player():
                continue
            elif search.has_newbie():
                unmatched_newbies.append(search)
            elif not first_opponent and search.failed_matching_attempts >= 1:
                first_opponent = search

        while len(unmatched_newbies) >= 2:
            newbie1 = unmatched_newbies.pop()
            newbie2 = unmatched_newbies.pop()
            self._match(newbie1, newbie2)
            searches_remaining_unmatched.discard(newbie1)
            searches_remaining_unmatched.discard(newbie2)

        can_match_last_newbie_with_first_opponent = unmatched_newbies and first_opponent
        if can_match_last_newbie_with_first_opponent:
            newbie = unmatched_newbies[0]
            self._match(newbie, first_opponent)
            searches_remaining_unmatched.discard(newbie)
            searches_remaining_unmatched.discard(first_opponent)

        return self.matches, list(searches_remaining_unmatched)
