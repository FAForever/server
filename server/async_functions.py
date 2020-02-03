"""
Some helper functions for common async tasks.
"""
import asyncio
from typing import Any, List, Type


async def gather_without_exceptions(
    tasks: List[asyncio.Task],
    *exceptions: Type[BaseException],
) -> List[Any]:
    """
    Call gather on a list of tasks, raising the first exception that dosen't
    match any of the specified exception classes.
    """
    results = []
    for fut in asyncio.as_completed(tasks):
        try:
            results.append(await fut)
        except exceptions:
            pass
    return results
