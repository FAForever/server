import asyncio
from unittest import mock

import pytest

from server.asyncio_extensions import (
    SpinLock,
    map_suppress,
    synchronized,
    synchronizedmethod
)
from tests.utils import fast_forward


class CustomError(Exception):
    pass


async def test_map_suppress(caplog):
    obj1 = mock.AsyncMock()
    obj2 = mock.AsyncMock()
    obj2.test.side_effect = CustomError("Test Exception")
    obj2.__str__.side_effect = lambda: "TestObject"

    with caplog.at_level("TRACE"):
        await map_suppress(
            lambda x: x.test(),
            [obj1, obj2]
        )

    obj1.test.assert_called_once()
    obj2.test.assert_called_once()
    assert "Unexpected error TestObject" in caplog.messages


async def test_map_suppress_message(caplog):
    obj1 = mock.AsyncMock()
    obj1.test.side_effect = CustomError("Test Exception")
    obj1.__str__.side_effect = lambda: "TestObject"

    with caplog.at_level("TRACE"):
        await map_suppress(
            lambda x: x.test(),
            [obj1],
            msg="when testing "
        )

    obj1.test.assert_called_once()
    assert "Unexpected error when testing TestObject" in caplog.messages


@fast_forward(15)
async def test_spinlock():
    lock = SpinLock(0.2)

    held_resource = False

    async def get_resource():
        nonlocal held_resource

        async with lock:
            assert held_resource is False
            assert lock.locked() is True

            held_resource = True
            await asyncio.sleep(1)
            held_resource = False

    await asyncio.gather(*[get_resource() for _ in range(10)])

    with pytest.raises(RuntimeError):
        lock.release()


async def test_spinlock_repr():
    lock = SpinLock()

    assert "unlocked" in repr(lock)
    await lock.acquire()
    assert "locked" in repr(lock) and "un" not in repr(lock)


@fast_forward(500)
async def test_synchronized():
    in_call = False

    @synchronized
    async def sleep_for_1s():
        nonlocal in_call

        assert in_call is False, "Multiple concurrent executions!"

        in_call = True
        await asyncio.sleep(1)
        in_call = False

    # 500 calls * 1 second each should sleep for 500 seconds
    await asyncio.gather(*[sleep_for_1s() for _ in range(500)])


@fast_forward(500)
async def test_synchronized_empty_args():
    in_call = False

    @synchronized()
    async def sleep_for_1s():
        nonlocal in_call

        assert in_call is False, "Multiple concurrent executions!"

        in_call = True
        await asyncio.sleep(1)
        in_call = False

    # 500 calls * 1 second each should sleep for 500 seconds
    await asyncio.gather(*[sleep_for_1s() for _ in range(500)])


@fast_forward(500)
async def test_synchronized_with_lock():
    lock = asyncio.Lock()
    in_call = False

    @synchronized(lock)
    async def sleep_for_1s():
        nonlocal in_call

        assert lock.locked(), "Lock was not held during function execution!"
        assert in_call is False, "Multiple concurrent executions!"

        in_call = True
        await asyncio.sleep(1)
        in_call = False

    # 500 calls * 1 second each should sleep for 500 seconds
    await asyncio.gather(*[sleep_for_1s() for _ in range(500)])


@fast_forward(500)
async def test_synchronizedmethod():
    class Test(object):
        def __init__(self):
            self.in_call = False

        @synchronizedmethod
        async def sleep_for_1s(self):
            assert self.in_call is False, "Multiple concurrent executions!"

            self.in_call = True
            await asyncio.sleep(1)
            self.in_call = False

    a = Test()
    b = Test()
    # Calls to different instances should not block eachother
    await asyncio.wait(
        [asyncio.create_task(a.sleep_for_1s()) for _ in range(500)] +
        [asyncio.create_task(b.sleep_for_1s()) for _ in range(500)],
        timeout=502
    )


@fast_forward(500)
async def test_synchronizedmethod_attrname():
    class Test(object):
        def __init__(self):
            self.in_call = False
            self._my_lock = asyncio.Lock()

        @synchronizedmethod("_my_lock")
        async def sleep_for_1s(self):
            assert self._my_lock.locked(), \
                "Lock was not held during function execution!"
            assert self.in_call is False, "Multiple concurrent executions!"

            self.in_call = True
            await asyncio.sleep(1)
            self.in_call = False

    a = Test()
    b = Test()
    # Calls to different instances should not block eachother
    await asyncio.wait(
        [asyncio.create_task(a.sleep_for_1s()) for _ in range(500)] +
        [asyncio.create_task(b.sleep_for_1s()) for _ in range(500)],
        timeout=502
    )
