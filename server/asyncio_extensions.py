"""
Some helper functions for common async tasks
"""

import asyncio
import inspect
import logging
from asyncio.locks import _ContextManagerMixin
from functools import wraps
from typing import (
    Any,
    AsyncContextManager,
    Callable,
    Coroutine,
    Optional,
    Protocol,
    cast,
    overload
)

logger = logging.getLogger(__name__)

AsyncFunc = Callable[..., Coroutine[Any, Any, Any]]
AsyncDecorator = Callable[[AsyncFunc], AsyncFunc]


class AsyncLock(Protocol, AsyncContextManager["AsyncLock"]):
    def locked(self) -> bool: ...
    async def acquire(self) -> bool: ...
    def release(self) -> None: ...


async def gather_without_exceptions(
    tasks: list[asyncio.Task],
    *exceptions: type[BaseException],
) -> list[Any]:
    """
    Run coroutines in parallel, raising the first exception that dosen't
    match any of the specified exception classes.
    """
    results = []
    for fut in asyncio.as_completed(tasks):
        try:
            results.append(await fut)
        except exceptions:
            logger.debug(
                "Ignoring error in gather_without_exceptions", exc_info=True
            )
    return results


# Based on python3.8 asyncio.Lock
# https://github.com/python/cpython/blob/6c6c256df3636ff6f6136820afaefa5a10a3ac33/Lib/asyncio/locks.py#L106
class SpinLock(_ContextManagerMixin):
    """
    An asyncio spinlock. The advantage of using this over asyncio.Lock is that
    it can be called accross multiple event loops at the cost of being less
    performant. As with any spinlock, it's best used in situations where
    concurrent access is unlikely.
    """

    def __init__(self, sleep_duration: float = 0.01):
        self.sleep_duration = sleep_duration
        self._locked = False

    def __repr__(self) -> str:
        res = super().__repr__()
        extra = 'locked' if self._locked else 'unlocked'
        return f'<{res[1:-1]} [{extra}]>'

    def locked(self) -> bool:
        """Return True if lock is acquired."""
        return self._locked

    async def acquire(self) -> bool:
        """
        Sleeps repeatedly for sleep_duration until the lock is unlocked, then
        sets it to locked and returns True.
        """
        while self._locked:
            await asyncio.sleep(self.sleep_duration)

        self._locked = True
        return True

    def release(self) -> None:
        """
        When invoked on an unlocked lock, a RuntimeError is raised.
        """
        if self._locked:
            self._locked = False
        else:
            raise RuntimeError('Lock is not acquired.')


class _partial(object):
    """
    Like functools.partial but applies arguments to the end.

    # Example:
    ```
    def foo(arg1, arg2):
        print(arg1, arg2)

    new = _partial(foo, "partially_applied")
    new("bar")
    # bar partially_applied
    ```
    """

    def __init__(self, func, *args):
        self.func = func
        self.args = args

    def __call__(self, *args):
        return self.func(*args, *self.args)


@overload
def synchronized() -> AsyncDecorator: ...
@overload
def synchronized(function: AsyncFunc) -> AsyncFunc: ...
@overload
def synchronized(lock: Optional[AsyncLock]) -> AsyncDecorator: ...


def synchronized(*args):
    """
    Ensure that a function will only execute in serial.

    # Params
    - `lock`: An instance of asyncio.Lock to use for synchronization.
    """
    # Invoked like @synchronized
    if args and inspect.isfunction(args[0]):
        return _synchronize(args[0])

    # Invoked like @synchronized() or @synchronized(args, ...)
    return _partial(_synchronize, *args)


def _synchronize(
    function: AsyncFunc,
    lock: Optional[AsyncLock] = None
) -> AsyncFunc:
    """Wrap an async function with an async lock."""
    @wraps(function)
    async def wrapped(*args, **kwargs):
        nonlocal lock

        if lock is None:
            lock = lock or cast(AsyncLock, asyncio.Lock())

        async with lock:
            return await function(*args, **kwargs)

    return wrapped


@overload
def synchronizedmethod() -> AsyncDecorator: ...
@overload
def synchronizedmethod(function: AsyncFunc) -> AsyncFunc: ...
@overload
def synchronizedmethod(lock_name: Optional[str]) -> AsyncDecorator: ...


def synchronizedmethod(*args):
    """
    Create a method that will be wrapped with an async lock.

    # Params
    - `attrname`: The name of the lock attribute that will be used. If the
        attribute doesn't exist or is None, a lock will be created. The default
        is to use a value based on the decorated function name.
    """
    # Invoked like @synchronizedmethod
    if args and inspect.isfunction(args[0]):
        return _synchronize_method(args[0])

    # Invoked like @synchronizedmethod() or @synchronizedmethod(args, ...)
    return _partial(_synchronize_method, *args)


def _synchronize_method(
    function: AsyncFunc,
    lock_name: Optional[str] = None
) -> AsyncFunc:
    """Wrap an async method with an async lock stored on the instance."""
    if lock_name is None:
        lock_name = f"#{function.__name__}_lock"

    @wraps(function)
    async def wrapped(obj, *args, **kwargs):
        lock = getattr(obj, lock_name, None)
        if lock is None:
            lock = asyncio.Lock()
            setattr(obj, lock_name, lock)

        async with lock:
            return await function(obj, *args, **kwargs)

    return wrapped
