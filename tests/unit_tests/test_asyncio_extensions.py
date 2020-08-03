import asyncio

import pytest
from asynctest import CoroutineMock

from server.asyncio_extensions import (
    gather_without_exceptions,
    synchronized,
    synchronizedmethod
)
from tests.utils import fast_forward

pytestmark = pytest.mark.asyncio


class CustomError(Exception):
    pass


async def raises_connection_error():
    raise ConnectionError("Test ConnectionError")


async def raises_connection_reset_error():
    raise ConnectionResetError("Test ConnectionResetError")


async def raises_custom_error():
    raise CustomError("Test Exception")


async def test_gather_without_exceptions():
    completes_correctly = CoroutineMock()

    with pytest.raises(CustomError):
        await gather_without_exceptions([
            raises_connection_error(),
            raises_custom_error(),
            completes_correctly()
        ], ConnectionError)

    completes_correctly.assert_called_once()


async def test_gather_without_exceptions_subclass():
    completes_correctly = CoroutineMock()

    await gather_without_exceptions([
        raises_connection_error(),
        raises_connection_reset_error(),
        completes_correctly()
    ], ConnectionError)

    completes_correctly.assert_called_once()


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
        [a.sleep_for_1s() for _ in range(500)] +
        [b.sleep_for_1s() for _ in range(500)],
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
        [a.sleep_for_1s() for _ in range(500)] +
        [b.sleep_for_1s() for _ in range(500)],
        timeout=502
    )
