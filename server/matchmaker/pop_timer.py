import asyncio
from collections import deque
from time import time
from typing import Callable, Deque

import server.metrics as metrics

from .. import config
from ..decorators import with_logger


@with_logger
class PopTimer(object):
    """ Calculates when the next pop should happen based on the rate of players
    queuing.

        timer = PopTimer("some_queue")
        # Pauses the coroutine until the next queue pop
        await timer.next_pop(lambda: 5)

    The timer will adjust the pop times in an attempt to maintain a fixed queue
    size on each pop. So generally, the more people are in the queue, the
    shorter the time will be.

    The player queue rate is based on a moving average over the last few pops.
    The exact size can be set in config.
    """
    def __init__(self, queue_name: str):
        self.queue_name = queue_name
        # Set up deque's for calculating a moving average
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
        metrics.matchmaker_queue_pop.labels(self.queue_name).set(int(time_remaining))
        await asyncio.sleep(time_remaining)
        num_players = get_num_players()
        metrics.matchmaker_players.labels(self.queue_name).set(num_players)

        self._last_queue_pop = time()
        self.next_queue_pop = self._last_queue_pop + self.time_until_next_pop(
            num_players, time_remaining
        )

    def time_until_next_pop(self, num_queued: int, time_queued: float) -> float:
        """ Calculate how long we should wait for the next queue to pop based
        on the current rate of ladder queues
        """
        # Calculate moving average of player queue rate
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
