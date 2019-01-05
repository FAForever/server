import gzip
import os
import random
import string
from unittest.mock import Mock

import pytest
import server.config
from aiohttp import web
from server.geoip_service import GeoIpService


@pytest.fixture
def fake_geoip_path(geoip_service) -> str:
    return '/tmp/fake_db.mmdb'


@pytest.fixture
def fake_geoip_service(geoip_service, fake_geoip_path) -> GeoIpService:
    geoip_service.file_path = fake_geoip_path
    return geoip_service


async def test_check_update(fake_geoip_service, fake_geoip_path):
    # Set the modified time to unixtime 0
    with open(fake_geoip_path, 'a'):
        os.utime(fake_geoip_path, (0, 0))
    server.config.GEO_IP_DATABASE_MAX_AGE_DAYS = 32
    fake_geoip_service.load_db = Mock()

    await fake_geoip_service.check_update_geoip_db()

    fake_geoip_service.download_geoip_db.assert_called_once_with()


async def test_do_update(fake_geoip_service, fake_geoip_path, loop):
    # Config variables
    PORT = 8137
    server.config.GEO_IP_DATABASE_URL = 'http://localhost:{}'.format(PORT)
    random_text = ''.join(random.choice(string.ascii_letters) for i in range(20))

    # Set up local http server for geoip service to connect to
    async def file_download(request):
        resp = web.StreamResponse()
        await resp.prepare(request)
        await resp.write(gzip.compress(random_text.encode()))
        await resp.write_eof()
        return resp

    app = web.Application()
    app.add_routes([web.get('/', file_download)])

    await loop.create_server(app.make_handler(), '127.0.0.1', PORT)

    # Test geoip update
    if os.path.isfile(fake_geoip_path):
        os.remove(fake_geoip_path)
    # Need to call it like this because the function is mocked
    await GeoIpService.download_geoip_db(fake_geoip_service)
    assert os.path.isfile(fake_geoip_path) is True
    with open(fake_geoip_path) as f:
        assert f.read() == random_text


async def test_country_on_invalid_address(geoip_service):
    country_code = geoip_service.country("127.0.0.1")
    assert country_code == ''


async def test_country_on_failed_db_load(geoip_service):
    geoip_service.db = None

    country_code = geoip_service.country("8.8.8.8")
    assert country_code == ''


async def test_load_db_not_raises(geoip_service):
    geoip_service.load_db()
