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

import pytest
from unittest import mock
from trueskill import Rating

logging.getLogger().setLevel(logging.DEBUG)

import os
os.environ['QUAMASH_QTIMPL'] = 'PySide'

import quamash

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
    parser.addoption('--slow', action='store_true', default=False,
                     help='Also run slow tests')
    parser.addoption('--aiodebug', action='store_true', default=False,
                     help='Enable asyncio debugging')
    parser.addoption('--mysql_host', action='store', default='127.0.0.1', help='mysql host to use for test database')
    parser.addoption('--mysql_username', action='store', default='root', help='mysql username to use for test database')
    parser.addoption('--mysql_password', action='store', default=None, help='mysql password to use for test database')
    parser.addoption('--mysql_database', action='store', default='faf_test', help='mysql database to use for tests')
    parser.addoption('--mysql_port',     action='store', default=3306, help='mysql port to use for tests')

def pytest_configure(config):
    if config.getoption('--aiodebug'):
        logging.getLogger('quamash').setLevel(logging.DEBUG)
        logging.captureWarnings(True)
    else:
        logging.getLogger('quamash').setLevel(logging.INFO)


def pytest_runtest_setup(item):
    """
    Skip tests if they are marked slow, and --slow isn't given on the commandline
    :param item:
    :return:
    """
    if getattr(item.obj, 'slow', None) and not item.config.getvalue('slow'):
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
    coro = asyncio.wait_for(testfn(**testargs), 5)

    try:
        loop.run_until_complete(coro)
    except RuntimeError as err:
        logging.error(err)
        raise err
    return True

@pytest.fixture(scope='session')
def application():
    from server.qt_compat import QtCore
    return QtCore.QCoreApplication([])

@pytest.fixture(scope='session', autouse=True)
def loop(request, application):
    loop = quamash.QEventLoop(application)
    loop.set_debug(True)
    asyncio.set_event_loop(loop)
    additional_exceptions = []

    def finalize():
        sys.excepthook = orig_excepthook
        try:
            loop.close()
        except KeyError:
            pass
        finally:
            asyncio.set_event_loop(None)
            for exc in additional_exceptions:
                if (
                        os.name == 'nt' and
                        isinstance(exc['exception'], WindowsError) and
                        exc['exception'].winerror == 6
                ):
                    # ignore Invalid Handle Errors
                    continue
                raise exc['exception']
    def except_handler(loop, ctx):
        additional_exceptions.append(ctx)
    def excepthook(type, *args):
        loop.stop()
    orig_excepthook = sys.excepthook
    sys.excepthook = excepthook
    loop.set_exception_handler(except_handler)
    request.addfinalizer(finalize)
    return loop

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
def db(sqlquery):
    # Since PySide does strict type checking, we cannot mock this directly
    from server.qt_compat import QtSql
    db = QtSql.QSqlDatabase()
    db.exec_ = lambda q: sqlquery
    db.isOpen = mock.Mock(return_value=True)
    return db

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

    @asyncio.coroutine
    def setup():
        cmd = 'SET storage_engine=MEMORY; drop database if exists {}; create database {}; use {}; source {};'.format(db, db, db, 'db-structure.sql')
        subprocess.check_call(['mysql', '-u{}'.format(user), '-p{}'.format(pw) if pw else '', '-e {}'.format(cmd)])
        subprocess.check_call(['mysql',
                               '-u{}'.format(user),
                               '-p{}'.format(pw) if pw else '',
                               '-e use {}; source {};'.format(db, 'tests/data/db-fixtures.sql')])

    def fin():
        pool.close()
        loop.run_until_complete(pool.wait_closed())
    request.addfinalizer(fin)

    loop.run_until_complete(setup())

    return pool

@pytest.fixture
def connected_game_socket():
    from server.qt_compat import QtNetwork
    game_socket = mock.Mock(spec=QtNetwork.QTcpSocket)
    game_socket.state = mock.Mock(return_value=QtNetwork.QTcpSocket.ConnectedState)
    game_socket.isValid = mock.Mock(return_value=True)
    return game_socket

@pytest.fixture
def transport():
    return mock.Mock(spec=asyncio.Transport)

@pytest.fixture
def game(players, db):
    from server.games import Game
    from server.abc.base_game import InitMode
    mock_parent = mock.Mock()
    mock_parent.db = db
    game = mock.create_autospec(spec=Game(1, mock_parent))
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
def game_service(loop, player_service):
    from server import GameService
    return GameService(player_service)
