import asyncio
import pytest
from unittest import mock

import os
from server import config

from tests.utils import fast_forward
from server.configuration_service import ConfigurationService

pytestmark = pytest.mark.asyncio


@fast_forward(20)
async def test_configuration_refresh(monkeypatch):
    service = ConfigurationService()
    config.CONFIGURATION_REFRESH_TIME = 10
    await service.initialize()

    assert config.DB_PASSWORD == "banana"
    monkeypatch.setenv("FAF_DB_PASSWORD", "apple")
    assert config.DB_PASSWORD == "banana"

    await asyncio.sleep(15)

    assert config.DB_PASSWORD == "apple"

    await service.shutdown()
