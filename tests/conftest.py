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

import pytest
from server.api.api_accessor import ApiAccessor
from server.config import DB_LOGIN, DB_PASSWORD, DB_PORT, DB_SERVER
from server.game_service import GameService
from server.geoip_service import GeoIpService
from server.matchmaker import MatchmakerQueue
from server.player_service import PlayerService
from server.rating import RatingType
from server.db import FAFDatabase
from tests.utils import EventLoopClockAdvancer

from asynctest import CoroutineMock

logging.getLogger().setLevel(logging.DEBUG)


def pytest_addoption(parser):
    parser.addoption('--aiodebug', action='store_true', default=False,
                     help='Enable asyncio debugging')
    parser.addoption('--mysql_host', action='store', default=DB_SERVER, help='mysql host to use for test database')
    parser.addoption('--mysql_username', action='store', default=DB_LOGIN, help='mysql username to use for test database')
    parser.addoption('--mysql_password', action='store', default=DB_PASSWORD, help='mysql password to use for test database')
    parser.addoption('--mysql_database', action='store', default='faf_test', help='mysql database to use for tests')
    parser.addoption('--mysql_port',     action='store', default=int(DB_PORT), help='mysql port to use for tests')


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


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
def mock_database(database):
    return database


@pytest.fixture
def database(request, event_loop):
    return _database(request, event_loop)


@pytest.fixture(scope='session', autouse=True)
def global_database(request):
    return _database(request, asyncio.get_event_loop())


def _database(request, event_loop):
    def opt(val):
        return request.config.getoption(val)
    host, user, pw, db, port = opt('--mysql_host'), opt('--mysql_username'), opt('--mysql_password'), opt('--mysql_database'), opt('--mysql_port')
    fdb = FAFDatabase(event_loop)

    db_fut = event_loop.create_task(
        fdb.connect(
            host=host,
            user=user,
            password=pw or None,
            port=port,
            db=db
        )
    )
    event_loop.run_until_complete(db_fut)

    def fin():
        event_loop.run_until_complete(fdb.close())
    request.addfinalizer(fin)

    return fdb


@pytest.fixture(scope='session', autouse=True)
def test_data(global_database):
    async def load_data():
        with open('tests/data/test-data.sql') as f:
            async with global_database.engine.acquire() as conn:
                await conn.execute(f.read())

    asyncio.get_event_loop().run_until_complete(load_data())


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
    mock_parent = mock.Mock()
    game = mock.create_autospec(spec=Game(uid, database, mock_parent, mock.Mock()))
    game.remove_game_connection = CoroutineMock()
    players.hosting.getGame = mock.Mock(return_value=game)
    players.joining.getGame = mock.Mock(return_value=game)
    players.peer.getGame = mock.Mock(return_value=game)
    game.hostPlayer = players.hosting
    game.init_mode = InitMode.NORMAL_LOBBY
    game.name = "Some game name"
    game.id = uid
    return game


@pytest.fixture
def player_factory():
    from server.players import Player, PlayerState

    def make(state=PlayerState.IDLE, global_rating=None, ladder_rating=None,
             numGames=0, ladder_games=0, **kwargs):
        ratings = {k: v for k, v in {
            RatingType.GLOBAL: global_rating,
            RatingType.LADDER_1V1: ladder_rating,
        }.items() if v is not None}

        games = {k: v for k, v in {
            RatingType.GLOBAL: numGames,
            RatingType.LADDER_1V1: ladder_games
        }.items() if v is not None}

        p = Player(ratings=ratings, game_count=games, **kwargs)
        p.state = state
        return p

    return make


@pytest.fixture
def players(player_factory):
    from server.players import PlayerState
    return mock.Mock(
        hosting=player_factory(login='Paula_Bean', player_id=1, state=PlayerState.HOSTING),
        peer=player_factory(login='That_Guy', player_id=2, state=PlayerState.JOINING),
        joining=player_factory(login='James_Kirk', player_id=3, state=PlayerState.JOINING)
    )


@pytest.fixture
def player_service(database):
    return PlayerService(database)


@pytest.fixture
def game_service(database, player_service, game_stats_service):
    return GameService(database, player_service, game_stats_service)


@pytest.fixture
def geoip_service() -> GeoIpService:
    return GeoIpService()


@pytest.fixture
def matchmaker_queue(game_service) -> MatchmakerQueue:
    return MatchmakerQueue("ladder1v1test", game_service)


@pytest.fixture()
def api_accessor():
    class FakeSession:
        def __init__(self):
            self.request = CoroutineMock(return_value=(200, 'test'))
            self.fetch_token = CoroutineMock()

    api_accessor = ApiAccessor()
    api_accessor.api_session.session = FakeSession()
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
