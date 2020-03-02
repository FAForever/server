import asyncio
from collections import OrderedDict, deque
from concurrent.futures import CancelledError
from datetime import datetime, timezone
from statistics import mean
from typing import Deque, Dict
import time
import functools

import server
import server.metrics as metrics

from ..decorators import with_logger
from .algorithm import make_matches
from .pop_timer import PopTimer
from .search import Match, Search


def timed_async_search(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        queue_name = self.queue_name
        metric = metrics.matchmaker_searches.labels(queue_name)
        start_time = time.monotonic()
        try:
            result = await func(self, *args, **kwargs)
            return result
        finally:
            metric.observe(time.monotonic() - start_time)

    return wrapper


@with_logger
class MatchmakerQueue:
    def __init__(
        self,
        queue_name: str,
        game_service: "GameService"
    ):
        self.game_service = game_service
        self.queue_name = queue_name

        self.queue: Dict[Search, Search] = OrderedDict()
        self._matches: Deque[Match] = deque()
        self._is_running = True

        self.timer = PopTimer(self.queue_name)
        asyncio.ensure_future(self.queue_pop_timer())
        self._logger.debug("MatchmakerQueue initialized for %s", queue_name)

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
        while self._is_running:
            await self.timer.next_pop(lambda: len(self.queue))

            await self.find_matches()

            number_of_matches = len(self._matches)
            metrics.matches.labels(self.queue_name).set(number_of_matches)

            #TODO: Move this into algorithm, then don't need to recalculate quality_with?
            # Probably not a major bottleneck though.
            for match in self._matches:
                metrics.match_quality.labels(self.queue_name).observe(
                    match[0].quality_with(match[1])
                )

            number_of_unmatched_searches = len(self.queue)
            metrics.unmatched_searches.labels(self.queue_name).set(number_of_unmatched_searches)

            # Any searches in the queue at this point were unable to find a
            # match this round and will have higher priority next round.

            self.game_service.mark_dirty(self)

    @timed_async_search
    async def search(self, search: Search) -> None:
        """
        Search for a match.

        Puts a search object into the Queue and awaits completion.

        :param player: Player to search for a matchup for
        """
        assert search is not None

        try:
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
        self._logger.info("Searching for matches: %s", self.queue_name)

        if len(self.queue) < 2:
            return

        # Call self.match on all matches and filter out the ones that were cancelled
        loop = asyncio.get_event_loop()
        new_matches = filter(
            lambda m: self.match(m[0], m[1]),
            await loop.run_in_executor(None, make_matches, self.queue.values())
        )
        self._matches.extend(new_matches)

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
            'queue_name': self.queue_name,
            'queue_pop_time': datetime.fromtimestamp(self.timer.next_queue_pop, timezone.utc).isoformat(),
            'boundary_80s': [search.boundary_80 for search in self.queue.values()],
            'boundary_75s': [search.boundary_75 for search in self.queue.values()]
        }

    def __repr__(self):
        return repr(self.queue)
