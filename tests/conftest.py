"""
This module is the 'top level' configuration for all the unit tests.

'Real world' fixtures are put here.
If a test suite needs specific mocked versions of dependencies,
these should be put in the ``conftest.py'' relative to it.
"""

import asyncio
import gc
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Iterable
from unittest import mock

import hypothesis
import pytest

from server.api.api_accessor import ApiAccessor
from server.api.oauth_session import OAuth2Session
from server.config import TRACE, config
from server.db import FAFDatabase
from server.game_service import GameService
from server.games import (
    CoopGame,
    FeaturedModType,
    Game,
    GameType,
    ValidityState
)
from server.geoip_service import GeoIpService
from server.lobbyconnection import LobbyConnection
from server.matchmaker import MatchmakerQueue
from server.message_queue_service import MessageQueueService
from server.oauth_service import OAuthService
from server.player_service import PlayerService
from server.players import Player, PlayerState
from server.rating import RatingType
from server.rating_service.rating_service import RatingService
from server.stats.achievement_service import AchievementService
from server.stats.event_service import EventService
from server.stats.game_stats_service import GameStatsService
from tests.utils import MockDatabase

logging.getLogger().setLevel(TRACE)
hypothesis.settings.register_profile(
    "nightly",
    max_examples=10_000,
    deadline=None,
    print_blob=True
)


def pytest_addoption(parser):
    parser.addoption(
        "--mysql_host",
        action="store",
        default=config.DB_SERVER,
        help="mysql host to use for test database",
    )
    parser.addoption(
        "--mysql_username",
        action="store",
        default=config.DB_LOGIN,
        help="mysql username to use for test database",
    )
    parser.addoption(
        "--mysql_password",
        action="store",
        default=config.DB_PASSWORD,
        help="mysql password to use for test database",
    )
    parser.addoption(
        "--mysql_database",
        action="store",
        default="faf_test",
        help="mysql database to use for tests",
    )
    parser.addoption(
        "--mysql_port",
        action="store",
        default=int(config.DB_PORT),
        help="mysql port to use for tests",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "addopts", "--strict-markers"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests (deselect with '-m \"not performance\"')"
    )
    config.addinivalue_line(
        "markers", "rabbitmq: marks tests as requiring a running instance of RabbitMQ"
    )
    config.addinivalue_line(
        "markers", "flaky: marks tests as known to be flaky"
    )


@pytest.fixture
def event_loop(request):
    """
    pytest-asyncio's event_loop fixture doesn't do any cleanup before closing
    the loop. This can make task errors from previous tests leak into the test
    output of later tests. We override the fixture here to implement the same
    cleanup as in asyncio.run().
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    # Cleanup code copied from the python3.9 version of asyncio.run()
    try:
        asyncio.runners._cancel_all_tasks(loop)
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())
    finally:
        loop.close()
        # Call the garbage collector to trigger ResourceWarning's as soon
        # as possible (these are triggered in various __del__ methods).
        # Without this, resources opened in one test can fail other tests
        # when the warning is generated.
        gc.collect()


@pytest.fixture(scope="session")
def caplog_context():
    """
    Returns a context manager for user controlled cleanup.

    `Hypothesis` tests should not use function scoped fixtures as they will not
    be reset between examples. Use this fixture instead to ensure that cleanup
    happens every time the test function is called.
    """
    @contextmanager
    def make_caplog_context(request):
        result = pytest.LogCaptureFixture(request.node, _ispytest=True)
        yield result
        result._finalize()

    return make_caplog_context


@pytest.fixture(scope="session")
def monkeypatch_context():
    return pytest.MonkeyPatch.context


@pytest.fixture(scope="session", autouse=True)
def test_data(request):
    async def _test_data():
        db = await global_database(request)
        with open("tests/data/test-data.sql") as f:
            async with db.acquire() as conn:
                await conn.execute(f.read().replace(":", r"\:"))

        await db.close()

    asyncio.run(_test_data())


async def global_database(request) -> FAFDatabase:
    def opt(val):
        return request.config.getoption(val)
    host, user, pw, name, port = (
        opt("--mysql_host"),
        opt("--mysql_username"),
        opt("--mysql_password"),
        opt("--mysql_database"),
        opt("--mysql_port")
    )

    return FAFDatabase(
        host=host,
        user=user,
        password=pw or "",
        port=port,
        db=name
    )


@pytest.fixture(scope="session")
def database_context():
    @asynccontextmanager
    async def make_database(request):
        def opt(val):
            return request.config.getoption(val)

        host, user, pw, name, port = (
            opt("--mysql_host"),
            opt("--mysql_username"),
            opt("--mysql_password"),
            opt("--mysql_database"),
            opt("--mysql_port")
        )
        db = MockDatabase(
            host=host,
            user=user,
            password=pw or "",
            port=port,
            db=name
        )
        await db.connect()

        yield db

        await db.close()

    return make_database


@pytest.fixture
async def database(request, database_context):
    async with database_context(request) as db:
        yield db


@pytest.fixture
def transport():
    return mock.Mock(spec=asyncio.Transport)


@pytest.fixture
def game(database, players):
    return make_game(database, 1, players)


GAME_UID = 1
COOP_GAME_UID = 1


@pytest.fixture
def ugame(database, players):
    global GAME_UID
    game = make_game(database, GAME_UID, players)
    GAME_UID += 1
    return game


@pytest.fixture
def coop_game(database, players):
    global COOP_GAME_UID
    game = make_game(database, COOP_GAME_UID, players, game_type=CoopGame)
    game.validity = ValidityState.COOP_NOT_RANKED
    game.leaderboard_saved = False
    COOP_GAME_UID += 1
    return game


def make_game(database, uid, players, game_type=Game):
    mock_parent = mock.AsyncMock()
    game = mock.create_autospec(
        spec=game_type(uid, database, mock_parent, mock.AsyncMock())
    )
    players.hosting.getGame = mock.AsyncMock(return_value=game)
    players.joining.getGame = mock.AsyncMock(return_value=game)
    players.peer.getGame = mock.AsyncMock(return_value=game)
    game.host = players.hosting
    game.game_type = GameType.CUSTOM
    game.name = "Some game name"
    game.id = uid
    return game


def make_player(
    login=None,
    state=PlayerState.IDLE,
    global_rating=None,
    ladder_rating=None,
    global_games=0,
    ladder_games=0,
    lobby_connection_spec=None,
    **kwargs
):
    ratings = {k: v for k, v in {
        RatingType.GLOBAL: global_rating,
        RatingType.LADDER_1V1: ladder_rating,
    }.items() if v is not None}

    games = {
        RatingType.GLOBAL: global_games,
        RatingType.LADDER_1V1: ladder_games
    }

    p = Player(login=login, ratings=ratings, game_count=games, **kwargs)
    p.state = state

    if lobby_connection_spec:
        if not isinstance(lobby_connection_spec, str):
            conn = mock.Mock(spec=lobby_connection_spec)
        elif lobby_connection_spec == "mock":
            conn = mock.Mock(spec=LobbyConnection)
        elif lobby_connection_spec == "auto":
            conn = mock.create_autospec(LobbyConnection)
        else:
            raise ValueError(f"Unknown spec type '{lobby_connection_spec}'")

        # lobby_connection is a weak reference, but we want the mock
        # to live for the full lifetime of the player object
        p.__owned_lobby_connection = conn
        p.lobby_connection = p.__owned_lobby_connection
        p.lobby_connection.player = p

    return p


@pytest.fixture(scope="session")
def player_factory():
    return make_player


@pytest.fixture
def players(player_factory):
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
async def rating_service(database, player_service, message_queue_service):
    service = RatingService(database, player_service, message_queue_service)
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
    database,
    player_service,
    game_stats_service,
    rating_service,
    message_queue_service
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
    service.download_geoip_db = mock.AsyncMock()
    await service.initialize()
    return service


@pytest.fixture(scope="session")
def queue_factory():
    queue_id = 0

    def make(
        name="Test Queue",
        mod="ladder1v1",
        team_size=1,
        rating_type=RatingType.GLOBAL,
        **kwargs
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
            **kwargs
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


@pytest.fixture
def api_accessor():
    session = mock.create_autospec(OAuth2Session)
    session.request.return_value = (200, "test")

    api_accessor = ApiAccessor()
    api_accessor.api_session.session = session
    return api_accessor


@pytest.fixture
def event_service(api_accessor):
    return EventService(api_accessor)


@pytest.fixture
def achievement_service(api_accessor):
    return AchievementService(api_accessor)


@pytest.fixture
def oauth_service():
    return OAuthService()


@pytest.fixture
def game_stats_service(event_service, achievement_service):
    return GameStatsService(event_service, achievement_service)


@pytest.fixture
def coturn_hosts() -> Iterable[str]:
    return ["a", "b", "c", "d"]


@pytest.fixture
def coturn_keys(coturn_hosts) -> Iterable[str]:
    return [f"secret_{host}" for host in coturn_hosts]


@pytest.fixture
def coturn_credentials() -> Iterable[str]:
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
