import asyncio
import time
from collections import OrderedDict
from concurrent.futures import CancelledError
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

import server.metrics as metrics

from ..asyncio_extensions import SpinLock, synchronized
from ..decorators import with_logger
from ..players import PlayerState
from .algorithm.team_matchmaker import TeamMatchMaker
from .map_pool import MapPool
from .pop_timer import PopTimer
from .search import Match, Search

MatchFoundCallback = Callable[[Search, Search, "MatchmakerQueue"], Any]


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
        on_match_found: MatchFoundCallback,
        name: str,
        queue_id: int,
        featured_mod: str,
        rating_type: str,
        team_size: int = 1,
        params: Optional[dict[str, Any]] = None,
        map_pools: Iterable[tuple[MapPool, Optional[int], Optional[int]]] = (),
    ):
        self.game_service = game_service
        self.name = name
        self.id = queue_id
        self.featured_mod = featured_mod
        self.rating_type = rating_type
        self.team_size = team_size
        self.params = params or {}
        self.map_pools = {info[0].id: info for info in map_pools}

        self._queue: dict[Search, None] = OrderedDict()
        self.on_match_found = on_match_found
        self._is_running = True

        self.timer = PopTimer(self)

        self.matchmaker = TeamMatchMaker()

    def add_map_pool(
        self,
        map_pool: MapPool,
        min_rating: Optional[int],
        max_rating: Optional[int]
    ) -> None:
        self.map_pools[map_pool.id] = (map_pool, min_rating, max_rating)

    def get_map_pool_for_rating(self, rating: float) -> Optional[MapPool]:
        for map_pool, min_rating, max_rating in self.map_pools.values():
            if min_rating is not None and rating < min_rating:
                continue
            if max_rating is not None and rating > max_rating:
                continue
            return map_pool

    def get_game_options(self) -> dict[str, Any]:
        return self.params.get("GameOptions") or None

    def initialize(self):
        asyncio.create_task(self.queue_pop_timer())

    @property
    def num_players(self) -> int:
        return sum(len(search.players) for search in self._queue.keys())

    async def queue_pop_timer(self) -> None:
        """ Periodically tries to match all Searches in the queue. The amount
        of time until next queue 'pop' is determined by the number of players
        in the queue.
        """
        self._logger.debug("MatchmakerQueue initialized for %s", self.name)
        while self._is_running:
            try:
                await self.timer.next_pop()

                await self.find_matches()

                number_of_unmatched_searches = len(self._queue)
                metrics.unmatched_searches.labels(self.name).set(
                    number_of_unmatched_searches
                )

                # Any searches in the queue at this point were unable to find a
                # match this round and will have higher priority next round.

                self.game_service.mark_dirty(self)
            except asyncio.CancelledError:
                break
            except Exception:
                self._logger.exception(
                    "Unexpected error during queue pop timer loop!"
                )
                # To avoid potential busy loops
                await asyncio.sleep(1)
        self._logger.info("%s queue stopped", self.name)

    async def search(self, search: Search) -> None:
        """
        Search for a match.

        Puts a search object into the queue and awaits completion.
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
            if search in self._queue:
                del self._queue[search]

    @synchronized(SpinLock(sleep_duration=1))
    async def find_matches(self) -> None:
        """
        Perform the matchmaking algorithm.

        Note that this function is synchronized such that only one instance of
        MatchmakerQueue can call this function at any given time. This is
        needed in order to safely enable multiqueuing.
        """
        self._logger.info("Searching for matches: %s", self.name)

        searches = list(self._queue.keys())

        if self.num_players < 2 * self.team_size:
            self._register_unmatched_searches(searches)
            return

        # Call self.match on all matches and filter out the ones that were cancelled
        loop = asyncio.get_running_loop()
        proposed_matches, unmatched_searches = await loop.run_in_executor(
            None,
            self.matchmaker.find,
            searches,
            self.team_size,
        )

        # filter out matches that were cancelled
        matches: list[Match] = []
        for match in proposed_matches:
            if self.match(match[0], match[1]):
                matches.append(match)
            else:
                unmatched_searches.extend(match)

        self._register_unmatched_searches(unmatched_searches)

        number_of_matches = len(matches)
        metrics.matches.labels(self.name).set(number_of_matches)

        for search1, search2 in matches:
            # TODO: Move this into algorithm, then don't need to recalculate
            # quality_with? Probably not a major bottleneck though.
            metrics.match_quality.labels(self.name).observe(
                search1.quality_with(search2)
            )
            try:
                self.on_match_found(search1, search2, self)
            except Exception:
                self._logger.exception("Match callback raised an exception!")

    def _register_unmatched_searches(
        self,
        unmatched_searches: list[Search],
    ):
        """
        Tells all unmatched searches that they went through a failed matching
        attempt.
        """
        for search in unmatched_searches:
            search.register_failed_matching_attempt()
            self._logger.debug(
                "Search %s remained unmatched at threshold %f in attempt number %s",
                search, search.match_threshold, search.failed_matching_attempts
            )

    def push(self, search: Search):
        """ Push the given search object onto the queue """

        self._queue[search] = None
        self.game_service.mark_dirty(self)

    def match(self, s1: Search, s2: Search) -> bool:
        """
        Mark the given two searches as matched

        # Returns
        `True` if matching succeeded or `False` if matching failed.
        """
        if s1.is_matched or s2.is_matched:
            return False
        if s1.is_cancelled or s2.is_cancelled:
            return False
        # Additional failsafe. Ideally this check will never fail.
        if any(
            player.state != PlayerState.SEARCHING_LADDER
            for player in s1.players + s2.players
        ):
            self._logger.warning(
                "Tried to match searches %s and %s while some players had "
                "invalid states: team1: %s team2: %s",
                s1, s2,
                list(p.state for p in s1.players),
                list(p.state for p in s2.players)
            )
            return False

        s1.match(s2)
        s2.match(s1)
        if s1 in self._queue:
            del self._queue[s1]
        if s2 in self._queue:
            del self._queue[s2]

        return True

    def shutdown(self):
        self._is_running = False

    def to_dict(self):
        """
        Return a fuzzy representation of the searches currently in the queue
        """
        return {
            "queue_name": self.name,
            "queue_pop_time": datetime.fromtimestamp(
                self.timer.next_queue_pop, timezone.utc
            ).isoformat(),
            "queue_pop_time_delta": self.timer.next_queue_pop - time.time(),
            "num_players": self.num_players,
            # TODO: Remove, the client should query the API for this
            "team_size": self.team_size,
        }

    def __repr__(self):
        return repr(self._queue)
