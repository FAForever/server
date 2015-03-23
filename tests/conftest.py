import asyncio
import logging
import os
import sys

from PySide.QtCore import QCoreApplication
import pytest
import mock
from PySide import QtCore, QtSql
from trueskill import Rating
from src.games_service import GamesService


if not hasattr(QtCore, 'Signal'):
    QtCore.Signal = QtCore.pyqtSignal

from PySide.QtNetwork import QTcpSocket
from src.players import PlayersOnline, Player
from games import Game

from src.JsonTransport import Transport

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s',
                                       '%M:%S'))
logging.getLogger('quamash').setLevel(logging.INFO)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.DEBUG)

import quamash


def async_test(f):
    def wrapper(*args, **kwargs):
        coro = asyncio.coroutine(f)
        future = coro(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete()
    return wrapper


def pytest_pycollect_makeitem(collector, name, obj):
    if name.startswith('test_') and asyncio.iscoroutinefunction(obj):
        return list(collector._genfunctions(name, obj))

def pytest_pyfunc_call(pyfuncitem):
    testfn = pyfuncitem.obj

    if not asyncio.iscoroutinefunction(testfn):
        return

    funcargs = pyfuncitem.funcargs
    testargs = {}
    for arg in pyfuncitem._fixtureinfo.argnames:
        testargs[arg] = funcargs[arg]
    coro = testfn(**testargs)

    loop = testargs.get('loop', asyncio.get_event_loop())
    try:
        loop.run_until_complete(coro)
    except RuntimeError as err:
        logging.warning(err)
    return True

@pytest.fixture(scope='session')
def application():
    return QCoreApplication([])

@pytest.fixture(scope='function')
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
                #raise exc['exception']
    def except_handler(loop, ctx):
        additional_exceptions.append(ctx)
    def excepthook(type, *args):
        loop.stop()
    orig_excepthook = sys.excepthook
    sys.excepthook = excepthook
    loop.set_exception_handler(except_handler)
    request.addfinalizer(finalize)
    return loop

@pytest.fixture()
def sqlquery():
    query = mock.MagicMock()
    query.exec_ = lambda: 0
    query.size = lambda: 0
    query.lastInsertId = lambda: 1
    query.prepare = lambda q: None
    query.addBindValue = lambda v: None
    return query

@pytest.fixture()
def db(sqlquery):
    # Since PySide does strict type checking, we cannot mock this directly
    db = QtSql.QSqlDatabase()
    db.exec_ = lambda q: sqlquery
    db.isOpen = mock.Mock(return_value=True)
    return db

@pytest.fixture
def patch_connectivity(monkeypatch):
    def set_to(level):
        @asyncio.coroutine
        def setter():
            yield from asyncio.sleep(0.001)
            return level
        monkeypatch.setattr('connectivity.TestPeer.determine_connectivity', setter)
    return set_to

@pytest.fixture
def connected_game_socket():
    game_socket = mock.Mock(spec=QTcpSocket)
    game_socket.state = mock.Mock(return_value=QTcpSocket.ConnectedState)
    game_socket.isValid = mock.Mock(return_value=True)
    return game_socket

@pytest.fixture
def transport():
    return mock.Mock(spec=Transport)

@pytest.fixture
def game(players, db):
    mock_parent = mock.Mock()
    mock_parent.db = db
    game = mock.create_autospec(spec=Game(1, mock_parent))
    players.hosting.getGame = mock.Mock(return_value=game)
    players.joining.getGame = mock.Mock(return_value=game)
    players.peer.getGame = mock.Mock(return_value=game)
    game.hostPlayer = players.hosting
    game.initMode = 0
    game.packetReceived = []
    game.gameName = "Some game name"
    game.uuid = 1
    return game

@pytest.fixture
def create_player():
    def make(login='', id=0, port=6112, action='HOST', ip='127.0.0.1', global_rating=Rating(1500, 250), ladder_rating=Rating(1500, 250)):
        p = mock.create_autospec(spec=Player(login))
        p.global_rating = global_rating
        p.ladder_rating = ladder_rating
        p.getAction = mock.Mock(return_value=action)
        p.getLogin = mock.Mock(return_value=login)
        p.getId = mock.Mock(return_value=id)
        p.getIp = mock.Mock(return_value=ip)
        p.ip = ip
        p.gamePort = port
        p.action = action
        p.id = id
        p.login = login
        p.address_and_port = "{}:{}".format(ip, port)
        return p
    return make

@pytest.fixture
def players(create_player):
    return mock.Mock(
        hosting=create_player(login='Paula_Bean', id=1, port=6112, action="HOST"),
        peer=create_player(login='That_Guy', id=2, port=6112, action="JOIN"),
        joining=create_player(login='James_Kirk', id=3, port=6112, action="JOIN")
    )

@pytest.fixture
def player_service(players):
    p = mock.Mock(spec=PlayersOnline())
    p.findByIp = mock.Mock(return_value=players.hosting)
    return p

@pytest.fixture
def games(game, players, db):
    service = mock.create_autospec(GamesService(players, db))
    service.find_by_id.return_value = game
    return service
