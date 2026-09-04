import asyncio
import functools

from .exhaust_callbacks import exhaust_callbacks


# Copied over from PR #113 of pytest-asyncio. It will probably be available in
# the library in a few months.
class EventLoopClockAdvancer:
    """
    A helper object that when called will advance the event loop's time. If the
    call is awaited, the caller task will wait an iteration for the update to
    wake up any awaiting handlers.
    """

    __slots__ = ("offset", "loop", "sleep_duration", "_base_time")

    def __init__(self, loop, sleep_duration=1e-6):
        self.offset = 0.0
        self._base_time = loop.time
        self.loop = loop
        self.sleep_duration = sleep_duration

        # incorporate offset timing into the event loop
        self.loop.time = self.time

    def time(self):
        """
        Return the time according to the event loop's clock. The time is
        adjusted by an offset.
        """
        return self._base_time() + self.offset

    async def __call__(self, seconds):
        """
        Advance time by a given offset in seconds. Returns an awaitable
        that will complete after all tasks scheduled for after advancement
        of time are proceeding.
        """
        # sleep so that the loop does everything currently waiting
        await asyncio.sleep(self.sleep_duration)

        if seconds > 0:
            # advance the clock by the given offset
            self.offset += seconds

            # Once the clock is adjusted, new tasks may have just been
            # scheduled for running in the next pass through the event loop
            await asyncio.sleep(self.sleep_duration)


def fast_forward(timeout):
    def deco(f):
        @functools.wraps(f)
        async def awaiter(*args, **kwargs):
            loop = asyncio.get_event_loop()
            advance_time = EventLoopClockAdvancer(loop)
            time = 0
            fut = asyncio.create_task(f(*args, **kwargs))

            while not fut.done() and time < timeout:
                await exhaust_callbacks()
                await advance_time(0.1)
                time += 0.1

            return await fut

        return awaiter
    return deco
