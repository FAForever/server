import asyncio
from collections import deque
from time import time
from typing import Callable, Deque

import server

from .. import config
from ..decorators import with_logger


@with_logger
class PopTimer(object):
    def __init__(self, queue_name: str):
        self.queue_name = queue_name
        self.last_queue_amounts: Deque[int] = deque(maxlen=config.QUEUE_POP_TIME_MOVING_AVG_SIZE)
        self.last_queue_times: Deque[float] = deque(maxlen=config.QUEUE_POP_TIME_MOVING_AVG_SIZE)

        self._last_queue_pop = time()
        # Optimistically schedule first pop for half of the max pop time
        self.next_queue_pop = self._last_queue_pop + (config.QUEUE_POP_TIME_MAX / 2)

    async def next_pop(self, get_num_players: Callable[[], int]):
        """ Wait for the timer to pop. get_num_players needs to return the current
        number of players in the queue. """

        time_remaining = self.next_queue_pop - time()
        self._logger.info("Next %s wave happening in %is", self.queue_name, time_remaining)
        server.stats.timing(
            "matchmaker.queue.pop", int(time_remaining),
            tags={'queue_name': self.queue_name}
        )
        await asyncio.sleep(time_remaining)
        num_players = get_num_players()
        server.stats.gauge(f"matchmaker.queue.{self.queue_name}.players", num_players)

        self._last_queue_pop = time()
        self.next_queue_pop = self._last_queue_pop + self.time_until_next_pop(
            num_players, time_remaining
        )

    def time_until_next_pop(self, num_queued: int, time_queued: float) -> float:
        """ Calculate how long we should wait for the next queue to pop based
        on the current rate of ladder queues
        """
        self.last_queue_amounts.append(num_queued)
        self.last_queue_times.append(time_queued)

        total_players = sum(self.last_queue_amounts)
        if total_players == 0:
            return config.QUEUE_POP_TIME_MAX

        total_times = sum(self.last_queue_times)
        if total_times:
            self._logger.debug(
                "Queue rate for %s: %f/s", self.queue_name,
                total_players / total_times
            )
        # Obtained by solving $ NUM_PLAYERS = rate * time $ for time.
        next_pop_time = config.QUEUE_POP_DESIRED_PLAYERS * total_times / total_players
        if next_pop_time > config.QUEUE_POP_TIME_MAX:
            self._logger.warning(
                "Required time (%.2fs) for %s is larger than max pop time (%ds). "
                "Consider increasing the max pop time",
                next_pop_time, self.queue_name, config.QUEUE_POP_TIME_MAX
            )
            return config.QUEUE_POP_TIME_MAX
        return next_pop_time
