import asyncio
import pytest
import logging
import mock

from PySide.QtNetwork import QTcpSocket
from players import playersOnline, Player
from games import Game

from JsonTransport import Transport

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s'))
logging.getLogger('quamash').setLevel(logging.INFO)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.DEBUG)

import quamash
from quamash import QApplication

@pytest.fixture(scope='session')
def application():
    return QApplication([])

@pytest.fixture()
def loop(request, application):
    loop = quamash.QEventLoop(application)
    asyncio.set_event_loop(loop)

    def finalize():
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)

    request.addfinalizer(finalize)
    return loop

@pytest.fixture
def patch_config(monkeypatch):
    monkeypatch.setattr('GameConnection.config',
                        mock.MagicMock(spec={'global':
                             mock.MagicMock(return_value={'lobby_ip': '192.168.0.1'})}))

@pytest.fixture
def patch_connectivity(monkeypatch):
    def set_to(level):
        @asyncio.coroutine
        def setter():
            yield from asyncio.sleep(0.001)
            return level
        monkeypatch.setattr('Connectivity.TestPeer.determine_connectivity', setter)
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
def game(players):
    game = mock.MagicMock(spec=Game(1))
    players.hosting.getGame = mock.Mock(return_value=game)
    players.joining.getGame = mock.Mock(return_value=game)
    players.peer.getGame = mock.Mock(return_value=game)
    game.hostPlayer = players.hosting
    game.getInitMode = lambda: 0
    game.packetReceived = []
    game.getGameName = lambda: "Some game name"
    game.getuuid = lambda: 1
    return game

def player(login, id, port, action):
    p = mock.MagicMock(spec=Player)
    p.getGamePort.return_value = port
    p.getAction = mock.Mock(return_value=action)
    p.getLogin = mock.Mock(return_value=login)
    p.getId = mock.Mock(return_value=id)
    p.getIp = mock.Mock(return_value='127.0.0.1')
    return p

@pytest.fixture
def players():
    return mock.Mock(
        hosting=player('Paula_Bean', 2, 6112, "HOST"),
        peer=player('That_Guy', 2, 6112, "JOIN"),
        joining=player('James_Kirk', 2, 6112, "JOIN")
    )

@pytest.fixture
def player_service(players):
    p = mock.Mock(spec=playersOnline())
    p.findByIp = mock.Mock(return_value=players.hosting)
    return p

@pytest.fixture
def games(game):
    return mock.Mock(
        getGameByUuid=mock.Mock(return_value=game)
    )
