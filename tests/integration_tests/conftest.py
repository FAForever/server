import asyncio
import hashlib
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, Tuple
from unittest import mock

import asynctest
import pytest
from aiohttp import web
from asynctest import exhaust_callbacks
from server import GameService, run_lobby_server
from server.db.models import login
from server.ladder_service import LadderService
from server.protocol import QDataStreamProtocol


@pytest.fixture
def mock_games():
    return asynctest.create_autospec(GameService)


@pytest.fixture
def ladder_service(mocker, database, game_service, event_loop):
    mocker.patch('server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX', 1)
    return LadderService(database, game_service, loop=event_loop)


@pytest.fixture
async def lobby_server(
    request, event_loop, database, player_service, game_service,
    geoip_service, ladder_service, policy_server
):
    with mock.patch(
        'server.lobbyconnection.FAF_POLICY_SERVER_BASE_URL',
        f'http://{policy_server.host}:{policy_server.port}'
    ):
        await asyncio.gather(
            player_service.initialize(),
            game_service.initialize(),
            ladder_service.initialize(),
            geoip_service.initialize()
        )

        ctx = await run_lobby_server(
            address=('127.0.0.1', None),
            database=database,
            geoip_service=geoip_service,
            player_service=player_service,
            game_service=game_service,
            ladder_service=ladder_service,
            nts_client=None,
            loop=event_loop
        )
        player_service.is_uniqueid_exempt = lambda id: True

        def fin():
            ctx.close()
            ladder_service.shutdown_queues()
            event_loop.run_until_complete(ctx.wait_closed())
            event_loop.run_until_complete(exhaust_callbacks(event_loop))

        request.addfinalizer(fin)

        yield ctx


@pytest.fixture
def policy_server(event_loop):
    host = 'localhost'
    port = 6080

    app = web.Application()
    routes = web.RouteTableDef()

    class Handle(object):
        def __init__(self):
            self.host = host
            self.port = port
            self.result = "honest"
            self.verify = mock.Mock()

    handle = Handle()

    @routes.post('/verify')
    async def token(request):
        # Register that the endpoint was called using a Mock
        handle.verify()

        await request.json()
        return web.json_response({'result': handle.result})

    app.add_routes(routes)

    runner = web.AppRunner(app)

    async def start_app():
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

    event_loop.run_until_complete(start_app())
    yield handle
    event_loop.run_until_complete(runner.cleanup())


@pytest.fixture
async def tmp_user(database):
    user_ids = defaultdict(lambda: 1)
    password_plain = "foo"
    password = hashlib.sha256(password_plain.encode()).hexdigest()

    async def make_user(name="TempUser"):
        user_id = user_ids[name]
        login_name = f"{name}{user_id}"
        async with database.acquire() as conn:
            await conn.execute(login.insert().values(
                login=login_name,
                email=f"{login_name}@example.com",
                password=password,
            ))
        user_ids[name] += 1
        return login_name, password_plain

    return make_user


async def connect_client(server) -> QDataStreamProtocol:
    return QDataStreamProtocol(
        *(await asyncio.open_connection(*server.sockets[0].getsockname()))
    )


async def perform_login(
    proto: QDataStreamProtocol, credentials: Tuple[str, str]
) -> None:
    login, pw = credentials
    pw_hash = hashlib.sha256(pw.encode('utf-8'))
    await proto.send_message({
        'command': 'hello',
        'version': '1.0.0-dev',
        'user_agent': 'faf-client',
        'login': login,
        'password': pw_hash.hexdigest(),
        'unique_id': 'some_id'
    })


async def read_until(
    proto: QDataStreamProtocol, pred: Callable[[Dict[str, Any]], bool]
) -> Dict[str, Any]:
    while True:
        msg = await proto.read_message()
        try:
            if pred(msg):
                return msg
        except (KeyError, ValueError):
            logging.getLogger().info("read_until predicate raised during message: {}".format(msg))
            pass


async def read_until_command(
    proto: QDataStreamProtocol,
    command: str,
    timeout: float = 60
) -> Dict[str, Any]:
    return await asyncio.wait_for(
        read_until(proto, lambda msg: msg.get('command') == command),
        timeout=timeout
    )


async def get_session(proto):
    await proto.send_message({'command': 'ask_session', 'user_agent': 'faf-client', 'version': '0.11.16'})
    msg = await read_until_command(proto, 'session')

    return msg['session']


async def connect_and_sign_in(credentials, lobby_server):
    proto = await connect_client(lobby_server)
    session = await get_session(proto)
    await perform_login(proto, credentials)
    hello = await read_until_command(proto, "welcome", timeout=120)
    player_id = hello['id']
    return player_id, session, proto
