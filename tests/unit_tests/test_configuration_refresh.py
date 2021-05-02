import asyncio
from unittest import mock

import pytest
from asynctest import CoroutineMock

from server import config
from server.configuration_service import ConfigurationService
from tests.utils import fast_forward

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def config_service(monkeypatch):
    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/test_conf.yaml")
    service = ConfigurationService()
    await service.initialize()

    yield service

    await service.shutdown()


async def test_configuration_refresh(monkeypatch):
    config.refresh()
    assert config.DB_PASSWORD == "banana"
    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/refresh_conf.yaml")
    assert config.DB_PASSWORD == "banana"

    config.refresh()

    assert config.DB_PASSWORD == "apple"


async def test_config_refresh_file_not_found(monkeypatch):
    config.refresh()
    assert config.DB_PASSWORD == "banana"

    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/nonexistent_conf.yaml")
    config.refresh()

    assert config.DB_PASSWORD == "banana"


async def test_config_refresh_empty_file(monkeypatch):
    config.refresh()
    assert config.DB_PASSWORD == "banana"

    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/empty_conf.yaml")
    config.refresh()

    assert config.DB_PASSWORD == "banana"


@fast_forward(20)
async def test_config_callback_on_change(config_service, monkeypatch):
    callback = mock.Mock()
    callback_coroutine = CoroutineMock()
    config.register_callback("DB_PASSWORD", callback)
    config.register_callback("CONTROL_SERVER_PORT", callback_coroutine)
    assert config.DB_PASSWORD == "banana"
    assert config.CONTROL_SERVER_PORT == 4000

    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/refresh_conf.yaml")
    await asyncio.sleep(10)

    assert config.DB_PASSWORD == "apple"
    assert config.CONTROL_SERVER_PORT == 4001
    callback.assert_called_once()
    callback_coroutine.assert_awaited_once()


@fast_forward(20)
async def test_config_no_callback_without_change(config_service, monkeypatch):
    callback = mock.Mock()
    config.register_callback("DB_PASSWORD", callback)
    assert config.DB_PASSWORD == "banana"

    await asyncio.sleep(10)

    assert config.DB_PASSWORD == "banana"
    callback.assert_not_called()
