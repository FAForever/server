"""
Helpers for executing async functions on a timer
"""

from datetime import datetime, timezone

from .timer import LazyIntervalTimer, Timer, at_interval


def datetime_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = (
    "LazyIntervalTimer",
    "Timer",
    "at_interval",
    "datetime_now",
)
