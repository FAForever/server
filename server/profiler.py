import asyncio
import cProfile
import logging

from server.config import config
from server.decorators import with_logger
from server.timing import at_interval


@with_logger
class Profiler:
    def __init__(
        self, interval, player_service, duration=2, max_count=300, outfile="profile.txt"
    ):
        self.profiler = cProfile.Profile()
        self.interval = interval
        self.duration = duration
        self.current_count = 0
        self.max_count = max_count

        self._player_service = player_service
        self._outfile = outfile

        self._running = False
        self._task = None
        self._loop = asyncio.get_running_loop()

    def start(self):
        self._running = True
        if self._task is None:
            self._task = asyncio.create_task(Profiler._next_run(self))

    async def _next_run(self):
        await asyncio.sleep(self.interval)

        if not self._running:
            return
        self.current_count += 1
        await self._run()

        if self.current_count < self.max_count and self._running:
            self._task = asyncio.create_task(Profiler._next_run(self))

    async def _run(self):
        if len(self._player_service) > 1000:
            self._logger.info(
                "Refusing to profile under high load %i/%i",
                self.current_count,
                self.max_count,
            )
            return

        self._logger.info("Starting profiler")
        self.profiler.enable()
        await asyncio.sleep(self.duration)
        self.profiler.disable()

        self._logger.info("Done profiling %i/%i", self.current_count, self.max_count)
        if self._outfile is not None:
            self.profiler.dump_stats(self._outfile)

    def cancel(self):
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None


def profiler_factory(player_service, start=True):
    async def make():
        """
        Intentionally asynchronous, since it is to be used as an on-change
        hook for `config.PROFILING_INTERVAL`, and coroutines will first be run
        after _all_ config variables have been loaded.
        """
        if (
            config.PROFILING_INTERVAL <= 0
            or config.PROFILING_DURATION <= 0
            or config.PROFILING_COUNT <= 0
        ):
            return

        profiler = Profiler(
            config.PROFILING_INTERVAL,
            player_service,
            duration=config.PROFILING_DURATION,
            max_count=config.PROFILING_COUNT,
        )
        if start:
            profiler.start()  # pragma: no cover
        return profiler

    return make
