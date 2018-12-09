"""
This module is the 'top level' configuration for all the unit tests.

'Real world' fixtures are put here.
If a test suite needs specific mocked versions of dependencies,
these should be put in the ``conftest.py'' relative to it.
"""

import asyncio

import logging
import subprocess
import sys

from server.api.api_accessor import ApiAccessor
from server.config import DB_SERVER, DB_LOGIN, DB_PORT, DB_PASSWORD

import pytest
from unittest import mock
from trueskill import Rating

logging.getLogger().setLevel(logging.DEBUG)

import os


def async_test(f):
    def wrapper(*args, **kwargs):
        coro = asyncio.coroutine(f)
        future = coro(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(future)
    return wrapper


def pytest_pycollect_makeitem(collector, name, obj):
    if name.startswith('test_') and asyncio.iscoroutinefunction(obj):
        return list(collector._genfunctions(name, obj))


def pytest_addoption(parser):
    parser.addoption('--noslow', action='store_true', default=False,
                     help="Don't run slow tests")
    parser.addoption('--aiodebug', action='store_true', default=False,
                     help='Enable asyncio debugging')
    parser.addoption('--mysql_host', action='store', default=DB_SERVER, help='mysql host to use for test database')
    parser.addoption('--mysql_username', action='store', default=DB_LOGIN, help='mysql username to use for test database')
    parser.addoption('--mysql_password', action='store', default=DB_PASSWORD, help='mysql password to use for test database')
    parser.addoption('--mysql_database', action='store', default='faf_test', help='mysql database to use for tests')
    parser.addoption('--mysql_port',     action='store', default=int(DB_PORT), help='mysql port to use for tests')


def pytest_configure(config):
    if config.getoption('--aiodebug'):
        logging.getLogger('quamash').setLevel(logging.DEBUG)
        logging.captureWarnings(True)
    else:
        logging.getLogger('quamash').setLevel(logging.INFO)


def pytest_runtest_setup(item):
    """
    Skip tests if they are marked slow, and --noslow is given on the commandline
    :param item:
    :return:
    """
    if getattr(item.obj, 'slow', None) and item.config.getvalue('noslow'):
        pytest.skip("slow test")

def pytest_pyfunc_call(pyfuncitem):
    testfn = pyfuncitem.obj

    if not asyncio.iscoroutinefunction(testfn):
        return

    funcargs = pyfuncitem.funcargs
    testargs = {}
    for arg in pyfuncitem._fixtureinfo.argnames:
        testargs[arg] = funcargs[arg]
    loop = testargs.get('loop', asyncio.get_event_loop())
    loop.set_debug(True)
    coro = asyncio.wait_for(testfn(**testargs), 5)

    try:
        loop.run_until_complete(coro)
    except RuntimeError as err:
        logging.error(err)
        raise err
    return True

@pytest.fixture(scope='session', autouse=True)
def loop(request):
    import server
    server.stats = mock.MagicMock()
    return asyncio.get_event_loop()

@pytest.fixture
def sqlquery():
    query = mock.MagicMock()
    query.exec_ = lambda: 0
    query.size = lambda: 0
    query.lastInsertId = lambda: 1
    query.prepare = mock.MagicMock()
    query.addBindValue = lambda v: None
    return query

@pytest.fixture
def mock_db_pool(loop, db_pool, autouse=True):
    return db_pool

@pytest.fixture(scope='session')
def db_pool(request, loop):
    import server

    def opt(val):
        return request.config.getoption(val)
    host, user, pw, db, port = opt('--mysql_host'), opt('--mysql_username'), opt('--mysql_password'), opt('--mysql_database'), opt('--mysql_port')
    pool_fut = asyncio.async(server.db.connect(loop=loop,
                                               host=host,
                                               user=user,
                                               password=pw or None,
                                               port=port,
                                               db=db))
    pool = loop.run_until_complete(pool_fut)


    def fin():
        pool.close()
        loop.run_until_complete(pool.wait_closed())
    request.addfinalizer(fin)

    return pool

@pytest.fixture
def transport():
    return mock.Mock(spec=asyncio.Transport)

@pytest.fixture
def game(players):
    from server.games import Game
    from server.abc.base_game import InitMode
    mock_parent = mock.Mock()
    game = mock.create_autospec(spec=Game(1, mock_parent, mock.Mock()))
    players.hosting.getGame = mock.Mock(return_value=game)
    players.joining.getGame = mock.Mock(return_value=game)
    players.peer.getGame = mock.Mock(return_value=game)
    game.hostPlayer = players.hosting
    game.init_mode = InitMode.NORMAL_LOBBY
    game.name = "Some game name"
    game.id = 1
    return game

@pytest.fixture
def create_player():
    from server.players import Player, PlayerState
    def make(login='', id=0, port=6112, state=PlayerState.HOSTING, ip='127.0.0.1', global_rating=Rating(1500, 250), ladder_rating=Rating(1500, 250)):
        p = mock.create_autospec(spec=Player(login))
        p.global_rating = global_rating
        p.ladder_rating = ladder_rating
        p.ip = ip
        p.game_port = port
        p.state = state
        p.id = id
        p.login = login
        p.address_and_port = "{}:{}".format(ip, port)
        return p
    return make

@pytest.fixture
def players(create_player):
    from server.players import PlayerState
    return mock.Mock(
        hosting=create_player(login='Paula_Bean', id=1, port=6112, state=PlayerState.HOSTING),
        peer=create_player(login='That_Guy', id=2, port=6112, state=PlayerState.JOINING),
        joining=create_player(login='James_Kirk', id=3, port=6112, state=PlayerState.JOINING)
    )

@pytest.fixture
def player_service(loop, players, db_pool):
    from server import PlayerService
    return PlayerService(db_pool)

@pytest.fixture
def game_service(loop, player_service, game_stats_service):
    from server import GameService
    return GameService(player_service, game_stats_service)

@pytest.fixture()
def api_accessor():
    class FakeRequestResponse:
        def __init__(self):
            self.status_code = 200
            self.text = "test"

    class FakeSession:
        def __init__(self, client):
            self.request = mock.Mock(return_value=FakeRequestResponse())
            self.get = mock.Mock(return_value=FakeRequestResponse())

        def fetch_token(self, token_url, client_id, client_secret):
            pass

    class SessionManager:
        def __init__(self):
            self.session = FakeSession(None)

        def __enter__(self):
            return self.session

        def __exit__(self, *args):
            pass

    api_accessor = ApiAccessor()
    api_accessor.api_session = SessionManager()
    return api_accessor

@pytest.fixture
def event_service(api_accessor):
    from server.stats.event_service import EventService
    return EventService(api_accessor)

@pytest.fixture
def achievement_service(api_accessor):
    from server.stats.achievement_service import AchievementService
    return AchievementService(api_accessor)

@pytest.fixture
def game_stats_service(event_service, achievement_service):
    from server.stats.game_stats_service import GameStatsService
    return GameStatsService(event_service, achievement_service)
