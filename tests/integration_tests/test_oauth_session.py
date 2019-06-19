import asyncio
import os

import pytest
from aiohttp import web
from aiohttp.client_exceptions import ClientResponseError
from oauthlib.oauth2.rfc6749.errors import MissingTokenError
from server.api.oauth_session import OAuth2Session


@pytest.fixture
def oauth2_session(oauth2_server):
    (host, port) = oauth2_server
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'Uh, yea I guess'

    yield OAuth2Session(
        'the_client_id',
        'the_client_secret',
        f'http://{host}:{port}/token'
    )
    del os.environ['OAUTHLIB_INSECURE_TRANSPORT']


@pytest.fixture
def oauth2_server(loop):
    host = 'localhost'
    port = 8080

    app = web.Application()
    routes = web.RouteTableDef()

    @routes.post('/token')
    async def token(request):
        data = await request.post()
        return await {
            'client_credentials': client_credentials,
            'refresh_token': refresh_token
        }.get(data.get('grant_type'))(data)

    async def client_credentials(data):
        if data.get('client_id') != 'the_client_id' or \
           data.get('client_secret') != 'the_client_secret':
            return web.Response(status=401, headers={'WWW-Authenticate': 'Git gud'})
        return web.json_response({
            'access_token': 'the_token',
            'refresh_token': 'the_refresh_token',
            'expires_in': 0
        })

    async def refresh_token(data):
        if data.get('client_id') != 'the_client_id' or \
           data.get('client_secret') != 'the_client_secret' or \
           data.get('refresh_token') != 'the_refresh_token':
            return web.Response(status=401, headers={'WWW-Authenticate': 'Git gud'})
        return web.json_response({
            'access_token': 'the_token',
            'refresh_token': 'the_refresh_token',
            'expires_in': 0
        })

    @routes.get('/endpoint')
    async def endpoint(request):
        if request.headers.get('Authorization') != 'Bearer the_token':
            return web.Response(status=401, headers={'WWW-Authenticate': 'Git gud'})
        return web.json_response({'message': 'You did it!'})

    app.add_routes(routes)

    runner = web.AppRunner(app)

    async def start_app():
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

    loop.run_until_complete(start_app())
    yield (host, port)
    loop.run_until_complete(runner.cleanup())


async def test_fetch_token(oauth2_session):
    await oauth2_session.fetch_token()

    assert oauth2_session.token == 'the_token'
    assert oauth2_session.refresh_token == 'the_refresh_token'


async def test_fetch_token_bad(oauth2_session):
    oauth2_session.client_id = 'bad_client_id'
    with pytest.raises(ClientResponseError):
        await oauth2_session.fetch_token()

    assert oauth2_session.token is None
    assert oauth2_session.refresh_token is None


async def test_auto_refresh(oauth2_session):
    await oauth2_session.fetch_token()

    assert oauth2_session.token == 'the_token'

    oauth2_session.token = 'something_else'
    # Wait for the auto refresh
    await asyncio.sleep(0.1)
    assert oauth2_session.token == 'the_token'


async def test_reqest(oauth2_session):
    await oauth2_session.fetch_token()
    resp = await oauth2_session.request('GET', 'http://localhost:8080/endpoint')
    assert resp == (200, {'message': 'You did it!'})


async def test_reqest_missing_token(oauth2_session):
    with pytest.raises(MissingTokenError):
        await oauth2_session.request('GET', 'the_url')
