import asyncio
import pytest

from tests.utils import fast_forward
from server.configuration_service import ConfigurationService

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def fast_config_service(monkeypatch):
    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/test_conf.yaml")
    service = ConfigurationService()
    await service.initialize()

    yield service

    await service.shutdown()


@fast_forward(20)
async def test_configuration_refresh_callbacks(
    fast_config_service, geoip_service, lobby_server, monkeypatch
):
    monkeypatch.setenv("CONFIGURATION_FILE", "tests/data/refresh_conf.yaml")

    await asyncio.sleep(15)

    assert "refreshed" in geoip_service.file_path
