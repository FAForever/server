import asyncio

from collections import OrderedDict, deque
from concurrent.futures import CancelledError

import server
from server.decorators import with_logger
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
        self._shutdown = False
        self._logger.debug("MatchmakerQueue initialized for %s", queue_name)

    async def iter_matches(self):
        """ Asynchronusly yields matches as they become available """

        while not self._shutdown:
            if not self._matches:
                await asyncio.sleep(1)
                continue

            yield self._matches.popleft()

    async def search(self, search: Search):
        """
        Search for a match.

        If a suitable match is found, immediately calls on_matched_with on both players.

        Otherwise, puts a search object into the Queue and awaits completion

        :param player: Player to search for a matchup for
        """
        assert search is not None

        with server.stats.timer('matchmaker.search'):
            try:
                if self.find_match(search):
                    return

                self._logger.debug("Found nobody searching, pushing to queue: %s", search)
                self.push(search)
                await search.await_match()
                self._logger.debug("Search complete: %s", search)
            except CancelledError:
                pass
            finally:
                # If the queue was cancelled, or some other error occured,
                # make sure to clean up.
                self.game_service.mark_dirty(self)
                if search.player in self.queue:
                    del self.queue[search.player]

    def find_match(self, search: Search) -> bool:
        self._logger.debug("Searching for matchup for %s", search.player)
        for opponent, opponent_search in self.queue.copy().items():
            if opponent == search.player:
                continue

            quality = search.quality_with(opponent_search)
            threshold = search.match_threshold
            self._logger.debug("Game quality between %s and %s: %f (threshold: %f)",
                               search.player, opponent, quality, threshold)
            if quality >= threshold:
                return self.match(search, opponent_search)

            return False

    def push(self, search: Search):
        """ Push the given search object onto the queue """

        self.queue[search.player] = search
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
        if s1.player in self.queue:
            del self.queue[s1.player]
        if s2.player in self.queue:
            del self.queue[s2.player]

        self._matches.append((s1, s2))
        self.game_service.mark_dirty(self)
        return True

    def shutdown(self):
        self._shutdown = True

    def __len__(self):
        return self.queue.__len__()

    def to_dict(self):
        """
        Return a fuzzy representation of the searches currently in the queue
        """
        return {
            'queue_name': self.queue_name,
            'boundary_80s': [search.boundary_80 for player, search in self.queue.items()],
            'boundary_75s': [search.boundary_75 for player, search in self.queue.items()]
        }

    def __repr__(self):
        return repr(self.queue)
