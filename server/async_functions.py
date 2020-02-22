"""
Some helper functions for common async tasks.
"""
import asyncio
import logging
from typing import Any, List, Type

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
