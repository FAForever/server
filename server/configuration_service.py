"""
Manages periodic reloading of config variables
"""

import asyncio

from .config import config
from .core import Service
from .decorators import with_logger
from .oauth_service import OAuthService


@with_logger
class ConfigurationService(Service):
    def __init__(self, oauth_service: OAuthService) -> None:
        self._logger.info("Configuration service created.")
        self._store = config
        self._task = None
        self.oauth_service = oauth_service

    async def initialize(self) -> None:
        self._task = asyncio.create_task(self._worker_loop())
        self._logger.info("Configuration service started.")

    async def _worker_loop(self) -> None:
        while True:
            self._logger.debug("Refreshing configuration variables")
            self._store.refresh()
            await self.oauth_service.retrieve_public_keys()
            await asyncio.sleep(self._store.CONFIGURATION_REFRESH_TIME)

    async def shutdown(self) -> None:
        if self._task is not None:
            self._logger.info("Configuration service stopping.")
            self._task.cancel()
        self._task = None
