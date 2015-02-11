import asyncio

@asyncio.coroutine
def wait_signal(signal, timeout=0.5):
    future = asyncio.Future()
    def fire():
        if not future.done():
            future.set_result(True)
    signal.connect(fire)
    yield from asyncio.wait_for(future, timeout)
