from unittest import mock
import aiomysql
import asyncio
import pytest
from server import PlayerService, GameService


def pytest_addoption(parser):
    parser.addoption('--mysql_host', action='store', default='127.0.0.1', help='mysql host to use for test database')
    parser.addoption('--mysql_username', action='store', default='root', help='mysql username to use for test database')
    parser.addoption('--mysql_password', action='store', default='', help='mysql password to use for test database')
    parser.addoption('--mysql_database', action='store', default='faf_test', help='mysql database to use for tests')

@pytest.fixture
def mock_db_pool(mock_db_pool):
    return mock.create_autospec(aiomysql.create_pool())

@pytest.fixture
def mock_players():
    return mock.create_autospec(PlayerService(mock_db_pool))

@pytest.fixture
def mock_games(mock_players, db):
    return mock.create_autospec(GameService(mock_players, db))

@pytest.fixture
def db_pool(request, loop):
    def opt(val):
        return request.config.getoption(val)
    host, user, pw, db = opt('--mysql_host'), opt('--mysql_username'), opt('--mysql_password'), opt('--mysql_database')
    pool = loop.run_until_complete(aiomysql.create_pool(host=host,
                                                        user=user,
                                                        password=pw,
                                                        db=db,
                                                        autocommit=True,
                                                        loop=loop,
                                                        minsize=1,
                                                        maxsize=1))

    @asyncio.coroutine
    def setup():
        with (yield from pool) as conn:
            cur = yield from conn.cursor()
            with open('db-structure.sql', 'r', encoding='utf-8') as data:
                yield from cur.execute('DROP DATABASE IF EXISTS `%s`;' % db)
                yield from cur.execute('CREATE DATABASE IF NOT EXISTS `%s`;' % db)
                yield from cur.execute("USE `%s`;" % db)
                yield from cur.execute(data.read())
            with open('tests/data/db-fixtures.sql', 'r', encoding='utf-8') as data:
                yield from cur.execute(data.read())
                yield from cur.close()

    def fin():
        pool.close()
        loop.run_until_complete(pool.wait_closed())
    request.addfinalizer(fin)

    loop.run_until_complete(setup())

    return pool
