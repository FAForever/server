import asyncio
from asyncio import coroutine
from unittest.mock import Mock


@asyncio.coroutine
def wait_signal(signal, timeout=0.5):
    future = asyncio.Future()
    def fire():
        if not future.done():
            future.set_result(True)
    signal.connect(fire)
    yield from asyncio.wait_for(future, timeout)


def CoroMock(**kwargs):
    coro = Mock(name="CoroutineResult", **kwargs)
    corofunc = Mock(name="CoroutineFunction", side_effect=coroutine(coro))
    corofunc.coro = coro
    return corofunc
