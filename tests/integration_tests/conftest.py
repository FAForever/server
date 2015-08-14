from unittest import mock
import aiomysql
import asyncio
import pytest


@pytest.fixture
def mock_players(mock_db_pool):
    from server import PlayerService
    m = mock.create_autospec(PlayerService(mock_db_pool))
    m.client_version_info = (0, None)
    return m

@pytest.fixture
def mock_games(mock_players, db):
    from server import GameService
    return mock.create_autospec(GameService(mock_players, db))

