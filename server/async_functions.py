"""
Some helper functions for common async tasks.
"""
import asyncio
from typing import Callable, List, Optional


async def gather_without_exceptions(
    tasks: List[asyncio.Task],
    *exc_classes: type,
    callback: Optional[Callable[[Exception], None]] = None
) -> None:
    """
    Call gather on a list of tasks, raising the first exception that dosen't
    match a any of the specified exception classes.

    If callback is set, then it will be called on any non-matching exceptions.
    This is useful if you need to process every exception and not just the
    first one.
    """
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception) and result.__class__ in exc_classes:
            if callback is None:
                raise result
            else:
                callback(result)
