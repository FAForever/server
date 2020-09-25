from contextlib import AbstractContextManager
from time import perf_counter
from unittest import mock

import asynctest
import pytest
from asynctest import CoroutineMock

from server import GameStatsService
from server.game_service import GameService
from server.gameconnection import GameConnection, GameConnectionState
from server.games import Game
from server.ladder_service import LadderService
from server.protocol import QDataStreamProtocol


@pytest.fixture
def game_connection(
    request,
    database,
    game,
    players,
    game_service,
    player_service,
    event_loop
):
    conn = GameConnection(
        asynctest.create_autospec(QDataStreamProtocol),
        ("localhost", 8001),
        database=database,
        game=game,
        player=players.hosting,
        player_service=player_service,
        games=game_service
    )

    conn.finished_sim = False

    def fin():
        event_loop.run_until_complete(conn.abort())

    request.addfinalizer(fin)
    return conn


@pytest.fixture
def mock_game_connection():
    return make_mock_game_connection()


def make_mock_game_connection(
    state=GameConnectionState.INITIALIZING,
    player=mock.Mock()
):
    gc = asynctest.create_autospec(GameConnection)
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
async def ladder_service(
    mocker,
    database,
    game_service: GameService,
):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 1)
    ladder_service = LadderService(database, game_service)
    await ladder_service.initialize()

    yield ladder_service

    await ladder_service.shutdown()


def add_connected_player(game: Game, player):
    game.game_service.player_service[player.id] = player
    gc = make_mock_game_connection(state=GameConnectionState.CONNECTED_TO_HOST, player=player)
    game.set_player_option(player.id, "Army", 0)
    game.set_player_option(player.id, "StartSpot", 0)
    game.set_player_option(player.id, "Team", 0)
    game.set_player_option(player.id, "Faction", 0)
    game.set_player_option(player.id, "Color", 0)
    game.add_game_connection(gc)
    return gc


def add_connected_players(game: Game, players):
    """
    Utility to add players with army and StartSpot indexed by a list
    """
    for army, player in enumerate(players):
        add_connected_player(game, player)
        game.set_player_option(player.id, "Army", army)
        game.set_player_option(player.id, "StartSpot", army)
        game.set_player_option(player.id, "Team", army)
        game.set_player_option(player.id, "Faction", 0)
        game.set_player_option(player.id, "Color", 0)
    game.host = players[0]


@pytest.fixture
def game_add_players(player_factory):
    def add(gameobj: Game, n: int, team: int = None):
        game = gameobj
        current = len(game.players)
        players = []
        for i in range(current, current+n):
            p = player_factory(
                player_id=i+1,
                login=f"Player {i + 1}",
                global_rating=(1500, 500),
                with_lobby_connection=False
            )
            players.append(p)

        add_connected_players(game, players)

        if team is not None:
            for p in players:
                game.set_player_option(p.id, "Team", team)

        return players

    return add


class Benchmark(AbstractContextManager):
    """A contextmanager for benchmarking a section of code.

    ## Usage:
    ```
    with Benchmark() as b:
        time.sleep(1)

    b.elapsed()
    ```"""

    def __init__(self):
        self.start = None
        self.end = None

    def __enter__(self) -> "Benchmark":
        self.start = perf_counter()
        return self

    def __exit__(self, ext_type, ext_val, ext_tb) -> bool:
        self.end = perf_counter()
        return False

    def elapsed(self):
        return self.end - self.start


@pytest.fixture
def bench():
    return Benchmark()
