from aiohttp import web
import gzip
import os
import random
import string
from unittest.mock import Mock

import server.config
from server.geoip_service import GeoIpService


async def test_check_update(geoip_service):
    path = '/tmp/fake_db.mmdb'
    with open(path, 'a'):
        os.utime(path, (0, 0))
    server.config.GEO_IP_DATABASE_MAX_AGE_DAYS = 32
    geoip_service.file_path = '/tmp/fake_db.mmdb'
    geoip_service.load_db = Mock()

    await geoip_service.check_update_geoip_db()

    geoip_service.download_geoip_db.assert_called_once_with()


async def test_do_update(geoip_service, loop):
    # Config variables
    PORT = 8137
    path = '/tmp/fake_db.mmdb'
    server.config.GEO_IP_DATABASE_URL = 'http://localhost:{}'.format(PORT)
    geoip_service.file_path = '/tmp/fake_db.mmdb'
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
    if os.path.isfile(path):
        os.remove(path)
    # Need to call it like this because the function is mocked
    await GeoIpService.download_geoip_db(geoip_service)
    assert os.path.isfile(path) is True
    with open(path) as f:
        assert f.read() == random_text
