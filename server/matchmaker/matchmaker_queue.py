import asyncio
from collections import OrderedDict, deque
from concurrent.futures import CancelledError
from datetime import datetime, timezone
from statistics import mean
from time import time
from typing import Deque, Dict

import server

from .. import config
from ..decorators import with_logger
from .algorithm import stable_marriage
from .search import Match, Search


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
        self.last_queue_amounts: Deque[int] = deque()
        self._is_running = True
        self._last_queue_pop = time()
        self.next_queue_pop = self._last_queue_pop + config.QUEUE_POP_TIME_MAX
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
            time_remaining = self.next_queue_pop - time()
            self._logger.info("Next %s wave happening in %is", self.queue_name, time_remaining)
            server.stats.timing("matchmaker.queue.pop", int(time_remaining), tags={'queue_name': self.queue_name})
            await asyncio.sleep(time_remaining)
            server.stats.gauge(f"matchmaker.queue.{self.queue_name}.players", len(self))

            self._last_queue_pop = time()
            self.next_queue_pop = self._last_queue_pop + self.time_until_next_pop()

            self.find_matches()
            server.stats.gauge(f"matchmaker.queue.{self.queue_name}.matches", len(self._matches))
            if self._matches:
                server.stats.gauge(
                    f"matchmaker.queue.{self.queue_name}.quality",
                    mean(map(lambda m: m[0].quality_with(m[1]), self._matches))
                )
            else:
                server.stats.gauge(f"matchmaker.queue.{self.queue_name}.quality", 0)

            # Any searches in the queue at this point were unable to find a
            # match this round and will have higher priority next round.

            self.game_service.mark_dirty(self)

    def time_until_next_pop(self) -> int:
        """ Calculate how long we should wait for the next queue to pop based
        on a moving average of the amount of people in the queue.

        Uses a simple inverse relationship. See

        https://www.desmos.com/calculator/v3tdrjbqub

        for an exploration of possible functions.
        """
        num_queued = len(self)
        self.last_queue_amounts.append(num_queued)
        if len(self.last_queue_amounts) > config.QUEUE_POP_TIME_MOVING_AVG_SIZE:
            self.last_queue_amounts.popleft()

        x = mean(self.last_queue_amounts)
        self._logger.debug("Moving average of %s queue size: %f", self.queue_name, x)
        # Essentially y = max_time / (x+1) with a scale factor
        return int(config.QUEUE_POP_TIME_MAX / (x / config.QUEUE_POP_TIME_SCALE_FACTOR + 1))

    async def search(self, search: Search) -> None:
        """
        Search for a match.

        Puts a search object into the Queue and awaits completion.

        :param player: Player to search for a matchup for
        """
        assert search is not None

        with server.stats.timer('matchmaker.search'):
            try:
                self.push(search)
                await search.await_match()
                self._logger.debug("Search complete: %s", search)
            except CancelledError:
                pass
            finally:
                # If the queue was cancelled, or some other error occured,
                # make sure to clean up.
                self.game_service.mark_dirty(self)
                if search in self.queue:
                    del self.queue[search]

    def find_matches(self) -> None:
        self._logger.info("Searching for matches: %s", self.queue_name)

        # Call self.match on all matches and filter out the ones that were canceled
        new_matches = filter(
            lambda m: self.match(m[0], m[1]),
            stable_marriage(self.queue.values())
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

    def __len__(self):
        return self.queue.__len__()

    def to_dict(self):
        """
        Return a fuzzy representation of the searches currently in the queue
        """
        return {
            'queue_name': self.queue_name,
            'queue_pop_time': datetime.fromtimestamp(self.next_queue_pop, timezone.utc).isoformat(),
            'boundary_80s': [search.boundary_80 for search in self.queue.values()],
            'boundary_75s': [search.boundary_75 for search in self.queue.values()]
        }

    def __repr__(self):
        return repr(self.queue)
