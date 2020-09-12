import hashlib
import os
import random
import string
import tarfile
import tempfile
from datetime import datetime
from io import BytesIO
from time import time
from unittest.mock import Mock

import pytest
from aiohttp import web

import server.config
from server.geoip_service import GeoIpService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fake_geoip_path(geoip_service) -> str:
    return "/tmp/fake_db.mmdb"


@pytest.fixture
def fake_geoip_service(geoip_service, fake_geoip_path) -> GeoIpService:
    geoip_service.file_path = fake_geoip_path
    return geoip_service


async def test_check_update(fake_geoip_service, fake_geoip_path):
    # Set the modified time to unixtime 0
    with open(fake_geoip_path, "a"):
        os.utime(fake_geoip_path, (0, 0))

    server.config.GEO_IP_DATABASE_MAX_AGE_DAYS = 32
    server.config.GEO_IP_LICENSE_KEY = "Anything"

    fake_geoip_service.load_db = Mock()
    fake_geoip_service.download_geoip_db.reset_mock()

    await fake_geoip_service.check_update_geoip_db()

    fake_geoip_service.download_geoip_db.assert_called_once_with()


async def test_check_file_exist(fake_geoip_service):
    with tempfile.NamedTemporaryFile() as f:
        # Set creation time into the past
        os.utime(f.name, (time() - 60, time() - 60))
        fake_geoip_service.file_path = f.name
        fake_geoip_service.load_db = Mock()
        fake_geoip_service.db = None
        fake_geoip_service.db_update_time = None

        fake_geoip_service.check_geoip_db_file_updated()

        assert fake_geoip_service.load_db.call_count == 1
        fake_geoip_service.db = Mock()
        fake_geoip_service.db_update_time = datetime.now()

        fake_geoip_service.check_geoip_db_file_updated()
        fake_geoip_service.check_geoip_db_file_updated()
        fake_geoip_service.check_geoip_db_file_updated()

        # The file shouldn't be reloaded until it is updated
        assert fake_geoip_service.load_db.call_count == 1

        os.utime(f.name, (time(), time()))

        fake_geoip_service.check_geoip_db_file_updated()

        assert fake_geoip_service.load_db.call_count == 2


async def test_do_update(fake_geoip_service, fake_geoip_path):
    # Config variables
    PORT = 8137
    server.config.GEO_IP_DATABASE_URL = f"http://localhost:{PORT}"
    server.config.GEO_IP_LICENSE_KEY = "Anything"
    random_text = "".join(random.choice(string.ascii_letters) for i in range(20))

    data = BytesIO()
    tar = tarfile.open(fileobj=data, mode="w:gz")
    tarinfo = tarfile.TarInfo("GeoLite2-Country.mmdb")
    tarinfo.size = len(random_text)
    tar.addfile(tarinfo, BytesIO(random_text.encode()))
    tar.close()
    data.seek(0)

    tarred_text = data.read()
    checksum = hashlib.md5(tarred_text).hexdigest()

    # Set up local http server for geoip service to connect to
    async def file_download(request):
        # md5 hash
        if request.rel_url.query.get("suffix").endswith("md5"):
            return web.Response(text=checksum)

        # Fake database
        resp = web.StreamResponse()
        await resp.prepare(request)
        await resp.write(tarred_text)
        await resp.write_eof()
        return resp

    app = web.Application()
    app.add_routes([web.get("/", file_download)])

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "localhost", PORT).start()

    # Test geoip update
    if os.path.isfile(fake_geoip_path):
        os.remove(fake_geoip_path)
    # Need to call it like this because the function is mocked
    await GeoIpService.download_geoip_db(fake_geoip_service)
    assert os.path.isfile(fake_geoip_path) is True
    with open(fake_geoip_path) as f:
        assert f.read() == random_text

    await runner.cleanup()


async def test_country_on_invalid_address(geoip_service):
    country_code = geoip_service.country("127.0.0.1")
    assert country_code == ""


async def test_country_on_failed_db_load(geoip_service):
    geoip_service.db = None

    country_code = geoip_service.country("8.8.8.8")
    assert country_code == ""


async def test_load_db_not_raises(geoip_service):
    geoip_service.load_db()
