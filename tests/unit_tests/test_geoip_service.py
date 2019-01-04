from aiohttp import web
from unittest.mock import Mock
import os
import random
import string

import server.config


async def test_check_update(geoip_service):
    path = '/tmp/fake_db.mmdb'
    with open(path, 'a'):
        os.utime(path, (0, 0))
    server.config.GEO_IP_DATABASE_MAX_AGE_DAYS = 32
    geoip_service.file_path = '/tmp/fake_db.mmdb'
    geoip_service.load_db = Mock()

    await geoip_service.check_update_geoip_db()

    geoip_service.do_update_geoip_db.assert_called_once_with()


async def test_do_update(geoip_service):
    PORT = 8137
    path = '/tmp/fake_db.mmdb'
    with open(path, 'a'):
        os.utime(path, (0, 0))
    server.config.GEO_IP_DATABASE_URL = 'http://localhost:{}'.format(PORT)
    geoip_service.file_path = '/tmp/fake_db.mmdb'
    random_text = ''.join(random.choice(string.printable) for i in range(20))

    async def file_download(request):
        return web.Response(text=random_text)

    app = web.Application()
    app.add_routes([web.get('/', file_download)])
    web.run_app(app, port=PORT)

    assert os.path.isfile(path) is False
    await geoip_service.do_update_geoip_db()
    assert os.path.isfile(path) is True
    with open(path) as f:
        assert f.read() == random_text
