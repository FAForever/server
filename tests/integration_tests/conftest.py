import asyncio
import hashlib
import logging
from unittest import mock

import pytest
from server import GameService, PlayerService, run_lobby_server
from server.ladder_service import LadderService
from server.protocol import QDataStreamProtocol


@pytest.fixture
def mock_players():
    m = mock.create_autospec(PlayerService())
    m.client_version_info = (0, None)
    return m


@pytest.fixture
def mock_games(mock_players):
    return mock.create_autospec(GameService(mock_players))


@pytest.fixture
def ladder_service(game_service):
    return LadderService(game_service)


@pytest.fixture
def lobby_server(request, loop, player_service, game_service, geoip_service, ladder_service):
    ctx = run_lobby_server(
        address=('127.0.0.1', None),
        geoip_service=geoip_service,
        player_service=player_service,
        games=game_service,
        ladder_service=ladder_service,
        nts_client=None,
        loop=loop
    )
    player_service.is_uniqueid_exempt = lambda id: True

    def fin():
        ctx.close()
        ladder_service.shutdown_queues()
        loop.run_until_complete(ctx.wait_closed())

    request.addfinalizer(fin)

    return ctx


async def connect_client(server):
    return QDataStreamProtocol(
        *(await asyncio.open_connection(*server.sockets[0].getsockname()))
    )


async def perform_login(proto, credentials):
    login, pw = credentials
    pw_hash = hashlib.sha256(pw.encode('utf-8'))
    proto.send_message({
        'command': 'hello',
        'version': '1.0.0-dev',
        'user_agent': 'faf-client',
        'login': login,
        'password': pw_hash.hexdigest(),
        'unique_id': 'some_id'
    })
    await proto.drain()


async def read_until(proto, pred):
    while True:
        msg = await proto.read_message()
        try:
            if pred(msg):
                return msg
        except (KeyError, ValueError):
            logging.getLogger().info("read_until predicate raised during message: {}".format(msg))
            pass


async def get_session(proto):
    proto.send_message({'command': 'ask_session', 'user_agent': 'faf-client', 'version': '0.11.16'})
    await proto.drain()
    msg = await proto.read_message()

    return msg['session']


async def connect_and_sign_in(credentials, lobby_server):
    proto = await connect_client(lobby_server)
    session = await get_session(proto)
    await perform_login(proto, credentials)
    hello = await read_until(proto, lambda msg: msg['command'] == 'welcome')
    player_id = hello['id']
    return player_id, session, proto
