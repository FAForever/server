import asyncio
import pytest
from unittest import mock

import yaml
from server import config

from tests.utils import fast_forward
from server.configuration_service import ConfigurationService

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def config_service(monkeypatch):
    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/test_conf.yaml")
    service = ConfigurationService()
    await service.initialize()

    yield service

    await service.shutdown()


@fast_forward(20)
async def test_configuration_refresh(config_service, monkeypatch):
    assert config.DB_PASSWORD == "banana"
    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/refresh_conf.yaml")
    assert config.DB_PASSWORD == "banana"

    await asyncio.sleep(3)

    assert config.DB_PASSWORD == "apple"


@fast_forward(20)
async def test_config_callback_on_change(config_service, monkeypatch):
    callback = mock.Mock()
    config.register_callback("DB_PASSWORD", callback)
    assert config.DB_PASSWORD == "banana"

    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/refresh_conf.yaml")
    await asyncio.sleep(10)

    assert config.DB_PASSWORD == "apple"
    callback.assert_called_once()


@fast_forward(20)
async def test_config_no_callback_without_change(config_service, monkeypatch):
    callback = mock.Mock()
    config.register_callback("DB_PASSWORD", callback)
    assert config.DB_PASSWORD == "banana"

    await asyncio.sleep(10)

    assert config.DB_PASSWORD == "banana"
    callback.assert_not_called()
