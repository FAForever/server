import pytest
import mock

from PySide.QtNetwork import QTcpSocket, QTcpServer, QLocalServer, QLocalSocket
from FaServerThread import FAServerThread

from GameConnection import GameConnection
from JsonTransport import Transport, QDataStreamJsonTransport
from games import Game
from players import playersOnline, Player

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

@pytest.fixture
def game_connection(game, player_service, players, games, transport, monkeypatch, connected_game_socket):
    monkeypatch.setattr('GameConnection.config',
                        mock.MagicMock(return_value={'global':
                                                         mock.MagicMock(return_value={'lobby_ip': '192.168.0.1'})}))
    conn = GameConnection(users=player_service, games=games, db=None, parent=None)
    conn.socket = connected_game_socket
    conn.transport = transport
    conn.player = players.hosting
    conn.game = game
    game_connection.lobby = mock.Mock(spec=FAServerThread)
    return conn

def test_accepts_valid_socket(game_connection, connected_game_socket):
    """
    :type game_connection: GameConnection
    :type connected_game_socket QTcpSocket
    """
    assert game_connection.accept(connected_game_socket) is True


def test_handle_action_GameState_idle_sends_CreateLobby(game_connection, players, games, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    game_connection.player = players.joining
    game_connection.handle_action('GameState', ['Idle'])
    games.getGameByUuid.assert_called_once_with(players.joining.getGame())
    transport.send_message.assert_any_call({'key': 'CreateLobby',
                                            'commands': [0, players.joining.getGamePort(),
                                                         players.joining.getLogin(), 2, 1]})

def test_handle_action_GameState_lobby_sends_HostGame(game_connection, players, game, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    game_connection.player = players.hosting
    game_connection.handle_action('GameState', ['Lobby'])
    transport.send_message.assert_any_call({'key': 'HostGame', 'commands': [str(game.getMapName())]})

def test_handle_action_GameState_lobby_sends_JoinGame(game_connection, players, game, transport):
    """
    :type game_connection: GameConnection
    :type transport Transport
    """
    game_connection.player = players.joining
    game_connection.handle_action('GameState', ['Lobby'])
    transport.send_message.assert_any_call({'key': 'JoinGame', 'commands': [
        str(game.getHostIp()),
        str(game.getHostName()),
        int(game.getHostId())
    ]})
    game.add_peer.assert_called_with(players.joining, game_connection)

def test_handle_action_ConnectedToHost(game, game_connection, players):
    """
    :type game Game
    :type game_connection GameConnection
    """
    game_connection.player = players.joining
    game_connection.handle_action('ConnectedToHost', [])
    game.add_connection.assert_called_once_with(players.joining, players.hosting)


def test_handle_action_Connected(game, game_connection, players):
    """
    :type game Game
    :type game_connection GameConnection
    """
    game_connection.player = players.joining
    game_connection.handle_action('Connected', [players.peer])
    game.add_connection.assert_called_once_with(players.joining, players.peer)


def test_handle_action_Connected_no_raise(game_connection, players):
    """
    :type game_connection GameConnection
    """
    game_connection.player = players.joining
    game_connection.handle_action('Connected', [])
    # Shouldn't raise an exception


def test_handle_action_Connected_no_raise2(game_connection, players):
    """
    :type game_connection GameConnection
    """
    game_connection.player = players.joining
    game_connection.handle_action('Connected', ['garbage', 'garbage2'])
    # Shouldn't raise an exception


def test_handle_action_PlayerOption(game, game_connection):
    """
    :type game Game
    :type game_connection GameConnection
    """
    game_connection.handle_action('PlayerOption', [1, 'Color', 2])
    game.setPlayerOption.assert_called_once_with(1, 'Color', 2)


def test_handle_action_PlayerOption_malformed_no_raise(game_connection):
    """
    :type game_connection GameConnection
    """
    game_connection.handle_action('PlayerOption', [1, 'Sheeo', 'Color', 2])
    # Shouldn't raise an exception


def test_handle_action_GameOption(game, game_connection):
    game_connection.handle_action('PlayerOption', [1, 'Color', 2])
    game.setPlayerOption.assert_called_once_with(1, 'Color', 2)

