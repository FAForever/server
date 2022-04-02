"""
Manages periodic reloading of config variables
"""

import asyncio

from .config import config
from .core import Service
from .decorators import with_logger


@with_logger
class ConfigurationService(Service):
    def __init__(self) -> None:
        self._store = config
        self._task = None

    async def initialize(self) -> None:
        self._task = asyncio.create_task(self._worker_loop())
        self._logger.info("Configuration service initialized")

    async def _worker_loop(self) -> None:
        while True:
            try:
                self._logger.debug("Refreshing configuration variables")
                self._store.refresh()
                await asyncio.sleep(self._store.CONFIGURATION_REFRESH_TIME)
            except Exception:
                self._logger.exception("Error while refreshing config")
                # To prevent a busy loop
                await asyncio.sleep(60)

    async def shutdown(self) -> None:
        if self._task is not None:
            self._logger.info("Configuration service stopping.")
            self._task.cancel()
        self._task = None
