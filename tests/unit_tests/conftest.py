from unittest import mock

import pytest
from server import GameStatsService
from server.game_service import GameService
from server.gameconnection import GameConnection, GameConnectionState
from server.games import Game
from server.geoip_service import GeoIpService
from server.ladder_service import LadderService
from asynctest import CoroutineMock


@pytest.fixture
def lobbythread():
    return mock.Mock(
        send=lambda obj: None
    )


@pytest.fixture
def game_connection(request, database, game, players, game_service, player_service):
    from server import GameConnection
    conn = GameConnection(
        database=database,
        game=game,
        player=players.hosting,
        protocol=mock.Mock(),
        player_service=player_service,
        games=game_service
    )

    conn.finished_sim = False

    def fin():
        conn.abort()

    request.addfinalizer(fin)
    return conn


@pytest.fixture
def mock_game_connection():
    return make_mock_game_connection()


def make_mock_game_connection(state=GameConnectionState.INITIALIZING, player=None):
    gc = mock.create_autospec(spec=GameConnection)
    gc.state = state
    gc.player = player
    gc.finished_sim = False
    return gc


@pytest.fixture
def game_stats_service():
    service = mock.Mock(spec=GameStatsService)
    service.process_game_stats = CoroutineMock()
    service.reset_mock()
    return service


@pytest.fixture
def ladder_service(request, mocker, database, game_service: GameService):
    mocker.patch('server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX', 1)

    ladder_service = LadderService(database, game_service)

    def fin():
        ladder_service.shutdown_queues()

    request.addfinalizer(fin)
    return ladder_service


@pytest.fixture
def geoip_service():
    service = GeoIpService()
    service.download_geoip_db = CoroutineMock()
    return service


def add_connected_player(game: Game, player):
    game.game_service.player_service[player.id] = player
    gc = make_mock_game_connection(state=GameConnectionState.CONNECTED_TO_HOST, player=player)
    game.set_player_option(player.id, 'Army', 0)
    game.set_player_option(player.id, 'StartSpot', 0)
    game.set_player_option(player.id, 'Team', 0)
    game.set_player_option(player.id, 'Faction', 0)
    game.set_player_option(player.id, 'Color', 0)
    game.add_game_connection(gc)
    return gc


def add_connected_players(game: Game, players):
    """
    Utility to add players with army and StartSpot indexed by a list
    """
    for army, player in enumerate(players):
        add_connected_player(game, player)
        game.set_player_option(player.id, 'Army', army)
        game.set_player_option(player.id, 'StartSpot', army)
        game.set_player_option(player.id, 'Team', army)
        game.set_player_option(player.id, 'Faction', 0)
        game.set_player_option(player.id, 'Color', 0)
    game.host = players[0]


@pytest.fixture
def game_add_players(player_factory):
    def add(gameobj: Game, n: int, team: int=None):
        game = gameobj
        current = len(game.players)
        players = []
        for i in range(current, current+n):
            p = player_factory(player_id=i+1, login=f'Player {i + 1}',
                               global_rating=(1500, 500))
            players.append(p)

        add_connected_players(game, players)

        if team is not None:
            for p in players:
                game.set_player_option(p.id, 'Team', team)

        return players

    return add
