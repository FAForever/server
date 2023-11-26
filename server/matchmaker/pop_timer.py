import asyncio
from collections import deque
from time import time

import server.metrics as metrics

from ..config import config
from ..decorators import with_logger


@with_logger
class PopTimer(object):
    """ Calculates when the next pop should happen based on the rate of players
    queuing.

        timer = PopTimer(some_queue)
        # Pauses the coroutine until the next queue pop
        await timer.next_pop()

    The timer will adjust the pop times in an attempt to maintain a fixed queue
    size on each pop. So generally, the more people are in the queue, the
    shorter the time will be.

    The player queue rate is based on a moving average over the last few pops.
    The exact size can be set in config.
    """

    def __init__(self, queue: "MatchmakerQueue"):
        self.queue = queue
        # Set up deque's for calculating a moving average
        self.last_queue_amounts: deque[int] = deque(maxlen=config.QUEUE_POP_TIME_MOVING_AVG_SIZE)
        self.last_queue_times: deque[float] = deque(maxlen=config.QUEUE_POP_TIME_MOVING_AVG_SIZE)

        self._last_queue_pop = time()
        # Optimistically schedule first pop for half of the max pop time
        self.next_queue_pop = self._last_queue_pop + (config.QUEUE_POP_TIME_MAX / 2)
        self._wait_task = None

    async def next_pop(self):
        """ Wait for the timer to pop. """

        time_remaining = self.next_queue_pop - time()
        self._logger.info("Next %s wave happening in %is", self.queue.name, time_remaining)
        metrics.matchmaker_queue_pop.labels(self.queue.name).set(int(time_remaining))

        self._wait_task = asyncio.create_task(asyncio.sleep(time_remaining))
        await self._wait_task

        num_players = self.queue.num_players
        metrics.matchmaker_players.labels(self.queue.name).set(num_players)

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
                "Queue rate for %s: %f/s", self.queue.name,
                total_players / total_times
            )

        players_per_match = self.queue.team_size * 2
        desired_players = config.QUEUE_POP_DESIRED_MATCHES * players_per_match
        # Obtained by solving $ NUM_PLAYERS = rate * time $ for time.
        next_pop_time = desired_players * total_times / total_players
        if next_pop_time > config.QUEUE_POP_TIME_MAX:
            self._logger.info(
                "Required time (%.2fs) for %s is larger than max pop time (%ds). "
                "Consider increasing the max pop time",
                next_pop_time, self.queue.name, config.QUEUE_POP_TIME_MAX
            )
            return config.QUEUE_POP_TIME_MAX

        if next_pop_time < config.QUEUE_POP_TIME_MIN:
            self._logger.warning(
                "Required time (%.2fs) for %s is lower than min pop time (%ds). ",
                next_pop_time, self.queue.name, config.QUEUE_POP_TIME_MIN
            )
            return config.QUEUE_POP_TIME_MIN

        return next_pop_time

    def cancel(self):
        if self._wait_task:
            self._wait_task.cancel()
