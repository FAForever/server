import asyncio
from asyncio.locks import Condition


class LoginThrottler:
    def __init__(self, capacity, rate_per_s):
        self._capacity = capacity
        self._rate_per_s = rate_per_s
        self._quota = self._capacity
        self._wait_lock = Condition()
        self._leak_coro = asyncio.ensure_future(self._leak())
        self._closing = False

    async def consume(self):
        if self._closing:
            return
        self._quota -= 1
        if self._quota < 0:
            async with self._wait_lock:
                await self._wait_lock.wait()

    async def _leak(self):
        while True:
            self._quota += self._rate_per_s
            self._quota = min(self._quota, self._capacity)
            async with self._wait_lock:
                self._wait_lock.notify(self._rate_per_s)
            await asyncio.sleep(1)

    async def close(self):
        self._leak_coro.cancel()
        self._closing = True
        async with self._wait_lock:
            self._wait_lock.notify_all()
