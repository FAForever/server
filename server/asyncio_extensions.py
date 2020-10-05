"""
Some helper functions for common async tasks.
"""
import asyncio
import inspect
import logging
from functools import wraps
from typing import Any, Callable, Coroutine, List, Optional, Type, overload

AsyncFunc = Callable[..., Coroutine[Any, Any, Any]]
AsyncDecorator = Callable[[AsyncFunc], AsyncFunc]

logger = logging.getLogger(__name__)


async def gather_without_exceptions(
    tasks: List[asyncio.Task],
    *exceptions: Type[BaseException],
) -> List[Any]:
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
def synchronized() -> AsyncDecorator:
    ...


@overload
def synchronized(function: AsyncFunc) -> AsyncFunc:
    ...


@overload
def synchronized(lock: Optional[asyncio.Lock]) -> AsyncDecorator:
    ...


def synchronized(*args):
    """
    Ensure that a function will only execute in serial.

    :param lock: An instance of asyncio.Lock to use for synchronization.
    """
    # Invoked like @synchronized
    if args and inspect.isfunction(args[0]):
        return _synchronize(args[0])

    # Invoked like @synchronized() or @synchronized(args, ...)
    return _partial(_synchronize, *args)


def _synchronize(
    function: AsyncFunc,
    lock: Optional[asyncio.Lock] = None
) -> AsyncFunc:
    """Wrap an async function with an async lock."""
    @wraps(function)
    async def wrapped(*args, **kwargs):
        nonlocal lock

        # During testing, functions are called from multiple loops
        if lock is None or lock._loop != asyncio.get_event_loop():
            lock = asyncio.Lock()

        async with lock:
            return await function(*args, **kwargs)

    return wrapped


@overload
def synchronizedmethod() -> AsyncDecorator:
    ...


@overload
def synchronizedmethod(function: AsyncFunc) -> AsyncFunc:
    ...


@overload
def synchronizedmethod(lock_name: Optional[str]) -> AsyncDecorator:
    ...


def synchronizedmethod(*args):
    """
    Create a method that will be wrapped with an async lock.

    :param attrname: The name of the lock attribute that will be used. If the
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
