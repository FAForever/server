import asyncio
from collections import OrderedDict, deque
from concurrent.futures import CancelledError
from time import time

import server
from server.decorators import with_logger

from .algorithm import time_until_next_pop, MAX_QUEUE_POP_TIME, stable_marriage
from .search import Search


@with_logger
class MatchmakerQueue:
    def __init__(
        self,
        queue_name: str,
        game_service: "GameService"
    ):
        self.game_service = game_service
        self.queue_name = queue_name
        self.rating_prop = 'ladder_rating'
        self.queue = OrderedDict()
        self._matches = deque()
        self._is_running = True
        self._last_queue_pop = time()
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

    async def queue_pop_timer(self):
        """ Periodically tries to match all Searches in the queue. The amount
        of time until next queue 'pop' is determined by the number of players
        in the queue.
        """
        next_pop = MAX_QUEUE_POP_TIME
        while self._is_running:
            time_elapsed = time() - self._last_queue_pop
            time_remaining = next_pop - time_elapsed
            if time_remaining > 0:
                await asyncio.sleep(time_remaining)

            self._last_queue_pop = time()
            next_pop = time_until_next_pop(num_queued=len(self))

            self.find_matches()

            # Any searches in the queue at this point were unable to find a
            # match this round and will have higher priority next round.

            self.game_service.mark_dirty(self)

    async def search(self, search: Search):
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

    def find_matches(self):
        self._logger.debug("Searching for matches: ", self.queue_name)

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

        self._matches.append((s1, s2))
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
            'boundary_80s': [search.boundary_80 for search in self.queue.values()],
            'boundary_75s': [search.boundary_75 for search in self.queue.values()]
        }

    def __repr__(self):
        return repr(self.queue)
