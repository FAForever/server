import asyncio
import time
from collections import OrderedDict, deque
from concurrent.futures import CancelledError
from datetime import datetime, timezone
from typing import Deque, Dict, Iterable, List, Optional, Tuple

import server.metrics as metrics

from ..decorators import with_logger
from .algorithm import make_matches, make_teams, make_teams_from_single
from .map_pool import MapPool
from .pop_timer import PopTimer
from .search import Match, Search


class MatchmakerSearchTimer:
    def __init__(self, queue_name):
        self.queue_name = queue_name

    def __enter__(self):
        self.start_time = time.monotonic()

    def __exit__(self, exc_type, exc_value, traceback):
        total_time = time.monotonic() - self.start_time
        if exc_type is None:
            status = "successful"
        elif exc_type is CancelledError:
            status = "cancelled"
        else:
            status = "errored"

        metric = metrics.matchmaker_searches.labels(self.queue_name, status)
        metric.observe(total_time)


@with_logger
class MatchmakerQueue:
    def __init__(
        self,
        game_service: "GameService",
        name: str,
        min_team_size=1,
        max_team_size=1,
        map_pools: Iterable[Tuple[MapPool, Optional[int], Optional[int]]] = ()
    ):
        self.game_service = game_service
        self.name = name
        self.min_team_size = min_team_size
        self.max_team_size = max_team_size
        self.map_pools = {info[0].id: info for info in map_pools}

        self.queue: Dict[Search, Search] = OrderedDict()
        self._matches: Deque[Match] = deque()
        self._is_running = True

        self.timer = PopTimer(self.name)

    def add_map_pool(
        self,
        map_pool: MapPool,
        min_rating: Optional[int],
        max_rating: Optional[int]
    ) -> None:
        self.map_pools[map_pool.id] = (map_pool, min_rating, max_rating)

    def get_map_pool_for_rating(self, rating: int) -> Optional[MapPool]:
        for map_pool, min_rating, max_rating in self.map_pools.values():
            if min_rating is not None and rating < min_rating:
                continue
            if max_rating is not None and rating > max_rating:
                continue
            return map_pool

    async def initialize(self):
        asyncio.create_task(self.queue_pop_timer())

    async def iter_matches(self):
        """ Asynchronously yields matches as they become available """

        while self._is_running:
            if not self._matches:
                # There are no matches so there is nothing to do
                await asyncio.sleep(1)
                continue

            # Yield the next available match to the caller
            yield self._matches.popleft()

    async def queue_pop_timer(self) -> None:
        """ Periodically tries to match all Searches in the queue. The amount
        of time until next queue 'pop' is determined by the number of players
        in the queue.
        """
        self._logger.debug("MatchmakerQueue initialized for %s", self.name)
        while self._is_running:
            await self.timer.next_pop(lambda: len(self.queue))

            await self.find_matches()

            number_of_matches = len(self._matches)
            metrics.matches.labels(self.name).set(number_of_matches)

            # TODO: Move this into algorithm, then don't need to recalculate quality_with?
            # Probably not a major bottleneck though.
            for search1, search2 in self._matches:
                metrics.match_quality.labels(self.name).observe(
                    search1.quality_with(search2)
                )

            number_of_unmatched_searches = len(self.queue)
            metrics.unmatched_searches.labels(self.name).set(number_of_unmatched_searches)

            # Any searches in the queue at this point were unable to find a
            # match this round and will have higher priority next round.

            self.game_service.mark_dirty(self)

    async def search(self, search: Search) -> None:
        """
        Search for a match.

        Puts a search object into the Queue and awaits completion.

        :param player: Player to search for a matchup for
        """
        assert search is not None

        try:
            with MatchmakerSearchTimer(self.name):
                self.push(search)
                await search.await_match()
            self._logger.debug("Search complete: %s", search)
        except CancelledError:
            pass
        finally:
            # If the queue was cancelled, or some other error occurred,
            # make sure to clean up.
            self.game_service.mark_dirty(self)
            if search in self.queue:
                del self.queue[search]

    async def find_matches(self) -> None:
        self._logger.info("Searching for matches: %s", self.name)

        if len(self.queue) < 2 * self.min_team_size:
            return

        searches = self.find_teams()

        # Call self.match on all matches and filter out the ones that were cancelled
        loop = asyncio.get_running_loop()
        new_matches = filter(
            lambda m: self.match(m[0], m[1]),
            await loop.run_in_executor(None, make_matches, searches)
        )
        self._matches.extend(new_matches)

    def find_teams(self) -> List[Search]:
        searches = []
        unmatched = list(self.queue.values())
        for size in reversed(range(self.min_team_size, self.max_team_size + 1)):
            need_team = []
            for search in unmatched:
                if len(search.players) == size:
                    searches.append(search)
                else:
                    need_team.append(search)

            if all(len(s.players) == 1 for s in need_team):
                teams, unmatched = make_teams_from_single(need_team, size)
            else:
                teams, unmatched = make_teams(need_team, size)
            searches.extend(teams)

            if not unmatched:
                break
        return searches

    def push(self, search: Search):
        """ Push the given search object onto the queue """

        self.queue[search] = search
        self.game_service.mark_dirty(self)

    def match(self, s1: Search, s2: Search) -> bool:
        """
        Mark the given two searches as matched
        :param s1:
        :param s2:
        :return:
        """
        if (s1.is_matched or s2.is_matched) or (s1.is_cancelled or s2.is_cancelled):
            return False
        s1.match(s2)
        s2.match(s1)
        if s1 in self.queue:
            del self.queue[s1]
        if s2 in self.queue:
            del self.queue[s2]

        return True

    def shutdown(self):
        self._is_running = False

    def to_dict(self):
        """
        Return a fuzzy representation of the searches currently in the queue
        """
        return {
            'queue_name': self.name,
            'queue_pop_time': datetime.fromtimestamp(self.timer.next_queue_pop, timezone.utc).isoformat(),
            'boundary_80s': [search.boundary_80 for search in self.queue.values()],
            'boundary_75s': [search.boundary_75 for search in self.queue.values()]
        }

    def __repr__(self):
        return repr(self.queue)
