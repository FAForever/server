"""
Some helper functions for common async tasks.
"""
import asyncio
from typing import List


async def gather_without_exceptions(
    tasks: List[asyncio.Task],
    *exc_classes: type,
) -> None:
    """
    Call gather on a list of tasks, raising the first exception that dosen't
    match any of the specified exception classes.
    """
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception) and result.__class__ not in exc_classes:
            raise result
