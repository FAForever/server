import asyncio
import pytest
from server.throttler import LoginThrottler
from tests.utils import fast_forward

pytestmark = pytest.mark.asyncio


@fast_forward(20)
async def test_throttling():
    throttler = LoginThrottler(10, 2)
    count = 0

    async def bump():
        nonlocal count
        await throttler.consume()
        count += 1

    work = asyncio.ensure_future(asyncio.gather(*[bump() for _ in range(20)]))

    await asyncio.sleep(0.5)
    assert count >= 10 and count < 20

    await asyncio.sleep(2)
    assert count < 20

    await work
    assert count == 20


@fast_forward(20)
async def test_throttling_all_released_at_close():
    throttler = LoginThrottler(10, 1)
    count = 0

    async def bump():
        nonlocal count
        await throttler.consume()
        count += 1

    work = asyncio.ensure_future(asyncio.gather(*[bump() for _ in range(20)]))
    await asyncio.sleep(0.5)

    loop = asyncio.get_event_loop()
    start = loop.time()

    await throttler.close()
    await work
    end = loop.time()
    assert end - start <= 1
