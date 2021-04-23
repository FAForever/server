"""
Analysis of application performance
"""

import asyncio
import cProfile
from asyncio import CancelledError

from server.config import config
from server.decorators import with_logger


@with_logger
class Profiler:
    def __init__(
        self,
        player_service,
        interval=config.PROFILING_INTERVAL,
        duration=config.PROFILING_DURATION,
        max_count=config.PROFILING_COUNT,
        outfile="server.profile",
    ):
        self.profiler = None
        self.interval = interval
        self.duration = duration
        self.profile_count = 0
        self.max_count = max_count

        self._player_service = player_service
        self._outfile = outfile

        self._running = False
        self._task = None

    def refresh(self):
        self.interval = config.PROFILING_INTERVAL
        self.duration = config.PROFILING_DURATION
        self.max_count = config.PROFILING_COUNT
        self.profile_count = 0

        self.cancel()
        if self.interval > 0 and self.duration > 0 and self.max_count > 0:
            self._start()

    def _start(self):
        self._running = True
        if self.profiler is None:
            self.profiler = cProfile.Profile()
        if self._task is None:
            self._task = asyncio.create_task(self._next_run())

    async def _next_run(self):
        await asyncio.sleep(self.interval)

        if self._running:
            try:
                await self._run()
            except CancelledError:
                pass

        if self.profile_count < self.max_count and self._running:
            self._task = asyncio.create_task(self._next_run())
        else:
            self.cancel()

    async def _run(self):
        if len(self._player_service) > 1500:
            self._logger.info(
                "Refusing to profile under high load %i/%i",
                self.profile_count,
                self.max_count,
            )
            return

        self.profile_count += 1

        self._logger.info("Starting profiler")
        self.profiler.enable()
        await asyncio.sleep(self.duration)
        self.profiler.disable()

        self._logger.info("Done profiling %i/%i", self.profile_count, self.max_count)
        if self._outfile is not None:
            self.profiler.dump_stats(self._outfile)

    def cancel(self):
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

        del self.profiler
        self.profiler = None
