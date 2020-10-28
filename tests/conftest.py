"""
This module is the 'top level' configuration for all the unit tests.

'Real world' fixtures are put here.
If a test suite needs specific mocked versions of dependencies,
these should be put in the ``conftest.py'' relative to it.
"""

import asyncio
import logging
from typing import Iterable
from unittest import mock

import asynctest
import pytest
from asynctest import CoroutineMock

from server.api.api_accessor import ApiAccessor
from server.api.oauth_session import OAuth2Session
from server.config import TRACE, config
from server.db import FAFDatabase
from server.game_service import GameService
from server.games import FeaturedModType
from server.geoip_service import GeoIpService
from server.lobbyconnection import LobbyConnection
from server.matchmaker import MatchmakerQueue
from server.message_queue_service import MessageQueueService
from server.player_service import PlayerService
from server.players import Player, PlayerState
from server.rating import RatingType
from server.rating_service.rating_service import RatingService
from tests.utils import MockDatabase

logging.getLogger().setLevel(TRACE)


def pytest_addoption(parser):
    parser.addoption("--mysql_host", action="store", default=config.DB_SERVER, help="mysql host to use for test database")
    parser.addoption("--mysql_username", action="store", default=config.DB_LOGIN, help="mysql username to use for test database")
    parser.addoption("--mysql_password", action="store", default=config.DB_PASSWORD, help="mysql password to use for test database")
    parser.addoption("--mysql_database", action="store", default="faf_test", help="mysql database to use for tests")
    parser.addoption("--mysql_port",     action="store", default=int(config.DB_PORT), help="mysql port to use for tests")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


@pytest.fixture(scope="session", autouse=True)
async def test_data(request):
    db = await global_database(request)
    with open("tests/data/test-data.sql") as f:
        async with db.acquire() as conn:
            await conn.execute(f.read())

    await db.close()


async def global_database(request):
    def opt(val):
        return request.config.getoption(val)
    host, user, pw, name, port = (
        opt("--mysql_host"),
        opt("--mysql_username"),
        opt("--mysql_password"),
        opt("--mysql_database"),
        opt("--mysql_port")
    )
    db = FAFDatabase(asyncio.get_running_loop())

    await db.connect(
        host=host,
        user=user,
        password=pw or None,
        port=port,
        db=name
    )

    return db


@pytest.fixture
async def database(request):
    def opt(val):
        return request.config.getoption(val)
    host, user, pw, name, port = (
        opt("--mysql_host"),
        opt("--mysql_username"),
        opt("--mysql_password"),
        opt("--mysql_database"),
        opt("--mysql_port")
    )
    db = MockDatabase(asyncio.get_running_loop())

    await db.connect(
        host=host,
        user=user,
        password=pw or None,
        port=port,
        db=name
    )

    yield db

    await db.close()


@pytest.fixture
def transport():
    return mock.Mock(spec=asyncio.Transport)


@pytest.fixture
def game(database, players):
    return make_game(database, 1, players)


GAME_UID = 1


@pytest.fixture
def ugame(database, players):
    global GAME_UID
    game = make_game(database, GAME_UID, players)
    GAME_UID += 1
    return game


def make_game(database, uid, players):
    from server.games import Game
    from server.abc.base_game import InitMode
    mock_parent = CoroutineMock()
    game = asynctest.create_autospec(spec=Game(uid, database, mock_parent,
                                               CoroutineMock()))
    players.hosting.getGame = CoroutineMock(return_value=game)
    players.joining.getGame = CoroutineMock(return_value=game)
    players.peer.getGame = CoroutineMock(return_value=game)
    game.host = players.hosting
    game.init_mode = InitMode.NORMAL_LOBBY
    game.name = "Some game name"
    game.id = uid
    return game


def make_player(
    state=PlayerState.IDLE,
    global_rating=None,
    ladder_rating=None,
    numGames=0,
    ladder_games=0,
    **kwargs
):
    ratings = {k: v for k, v in {
        RatingType.GLOBAL: global_rating,
        RatingType.LADDER_1V1: ladder_rating,
    }.items() if v is not None}

    games = {
        RatingType.GLOBAL: numGames,
        RatingType.LADDER_1V1: ladder_games
    }

    p = Player(ratings=ratings, game_count=games, **kwargs)
    p.state = state
    return p


@pytest.fixture(scope="session")
def player_factory():
    def make(
        login=None,
        state=PlayerState.IDLE,
        global_rating=None,
        ladder_rating=None,
        numGames=0,
        ladder_games=0,
        with_lobby_connection=False,
        **kwargs
    ):
        p = make_player(
            state=state,
            global_rating=global_rating,
            ladder_rating=ladder_rating,
            numGames=numGames,
            ladder_games=ladder_games,
            login=login,
            **kwargs
        )

        if with_lobby_connection:
            # lobby_connection is a weak reference, but we want the mock
            # to live for the full lifetime of the player object
            p.__owned_lobby_connection = asynctest.create_autospec(LobbyConnection)
            p.lobby_connection = p.__owned_lobby_connection
        return p

    return make


@pytest.fixture
def players(player_factory):
    from server.players import PlayerState
    return mock.Mock(
        hosting=player_factory("Paula_Bean", player_id=1, state=PlayerState.HOSTING),
        peer=player_factory("That_Guy", player_id=2, state=PlayerState.JOINING),
        joining=player_factory("James_Kirk", player_id=3, state=PlayerState.JOINING)
    )


@pytest.fixture
async def player_service(database):
    player_service = PlayerService(database)
    await player_service.initialize()
    return player_service


@pytest.fixture
async def rating_service(database, player_service):
    service = RatingService(database, player_service)
    await service.initialize()

    yield service

    await service.shutdown()


@pytest.fixture
async def message_queue_service():
    service = MessageQueueService()
    await service.initialize()

    yield service

    await service.shutdown()


@pytest.fixture
async def game_service(
    database, player_service, game_stats_service,
    rating_service, message_queue_service
):
    game_service = GameService(
        database,
        player_service,
        game_stats_service,
        rating_service,
        message_queue_service,
    )
    await game_service.initialize()
    return game_service


@pytest.fixture
async def geoip_service() -> GeoIpService:
    service = GeoIpService()
    service.download_geoip_db = CoroutineMock()
    await service.initialize()
    return service


@pytest.fixture(scope="session")
def queue_factory():
    queue_id = 0

    def make(
        name="Test Queue",
        mod="ladder1v1",
        team_size=1,
        rating_type=RatingType.GLOBAL
    ):
        nonlocal queue_id
        queue_id += 1
        return MatchmakerQueue(
            game_service=mock.Mock(),
            on_match_found=mock.Mock(),
            name=name,
            queue_id=queue_id,
            featured_mod=mod,
            rating_type=rating_type,
            team_size=team_size,
        )
    return make


@pytest.fixture
def matchmaker_queue(game_service) -> MatchmakerQueue:
    queue = MatchmakerQueue(
        game_service,
        mock.Mock(),
        "ladder1v1test",
        FeaturedModType.LADDER_1V1,
        RatingType.LADDER_1V1,
        1
    )
    return queue


@pytest.fixture()
def api_accessor():
    session = asynctest.create_autospec(OAuth2Session)
    session.request.return_value = (200, "test")

    api_accessor = ApiAccessor()
    api_accessor.api_session.session = session
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


@pytest.fixture
def coturn_hosts() -> Iterable:
    return ["a", "b", "c", "d"]


@pytest.fixture
def coturn_keys(coturn_hosts) -> Iterable:
    keys_list = []
    for host in coturn_hosts:
        keys_list.append(f"secret_{host}")
    return keys_list


@pytest.fixture
def coturn_credentials() -> Iterable:
    return [
        "mO/6NHZaG4fwCf7mVuaWNRS7Atw=",
        "uSjJUafCX3fEQTGK3NI+mUe6UDo=",
        "I5BcpufNrBb4JDj80KY/7VATNis=",
        "4wYEgoPz2MHf35Fva8NWulI3vVU="
    ]


@pytest.fixture
def twilio_sid():
    return "a"


@pytest.fixture
def twilio_token():
    return "token_a"
