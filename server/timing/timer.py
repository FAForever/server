"""
This code is a modified version of Gael Pasgrimaud's library `aiocron`.

See the original code here:
https://github.com/gawel/aiocron/blob/e82a53c3f9a7950209cee7b3e493204c1dfc8b12/aiocron/__init__.py
"""

import asyncio
import functools


async def null_callback(*args):
    return args


def wrap_func(func):
    """wrap in a coroutine"""
    if not asyncio.iscoroutinefunction(func):
        return asyncio.coroutine(func)
    return func


class Timer(object):
    """Schedules a function to be called asynchronously on a fixed interval"""

    def __init__(self, interval, func=None, args=(), start=False, loop=None):
        self.interval = interval
        if func is not None:
            self.func = func if not args else functools.partial(func, *args)
        else:
            self.func = null_callback
        self.cron = wrap_func(self.func)
        self.auto_start = start
        self.handle = self.future = None
        self.loop = loop if loop is not None else asyncio.get_running_loop()
        if start and self.func is not null_callback:
            self.handle = self.loop.call_soon_threadsafe(self.start)

    def start(self):
        """Start scheduling"""
        self.stop()
        self.handle = self.loop.call_later(self.get_delay(), self.call_next)

    def stop(self):
        """Stop scheduling"""
        if self.handle is not None:
            self.handle.cancel()
        self.handle = self.future = None

    def get_delay(self):
        """Return next interval to wait between calls"""
        return self.interval

    def call_next(self):
        """Set next hop in the loop. Call task"""
        if self.handle is not None:
            self.handle.cancel()
        self.handle = self.loop.call_later(self.get_delay(), self.call_next)
        self.call_func()

    def call_func(self, *args, **kwargs):
        """Called. Take care of exceptions using gather"""
        asyncio.gather(
            self.cron(*args, **kwargs),
            loop=self.loop, return_exceptions=True
        ).add_done_callback(self.set_result)

    def set_result(self, result):
        """Set future's result if needed (can be an exception).
        Else raise if needed."""
        result = result.result()[0]
        if self.future is not None:
            if isinstance(result, Exception):
                self.future.set_exception(result)
            else:
                self.future.set_result(result)
            self.future = None
        elif isinstance(result, Exception):
            raise result

    def __call__(self, func):
        """Used as a decorator"""
        self.func = func
        self.cron = wrap_func(func)
        if self.auto_start:
            self.loop.call_soon_threadsafe(self.start)
        return self

    def __str__(self):
        return f"{self.interval} {self.func}"

    def __repr__(self):
        return f"<Timer {str(self)}>"


def at_interval(interval, func=None, args=(), start=True, loop=None):
    return Timer(interval, func=func, args=args, start=start, loop=loop)
