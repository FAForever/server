"""
Some helper functions for common async tasks.
"""
import asyncio
from typing import Any, List


async def gather_without_exceptions(
    tasks: List[asyncio.Task],
    *exceptions: type,
) -> List[Any]:
    """
    Call gather on a list of tasks, raising the first exception that dosen't
    match any of the specified exception classes.
    """
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            # Check if this exception is an instance (maybe subclass) that
            # should be ignored
            for exc_type in exceptions:
                if not isinstance(result, exc_type):
                    raise result
    return results
