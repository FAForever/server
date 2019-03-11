from unittest import mock

import pytest
from server import GameService, PlayerService


@pytest.fixture
def mock_players(db_engine):
    m = mock.create_autospec(PlayerService())
    m.client_version_info = (0, None)
    return m


@pytest.fixture
def mock_games(mock_players):
    return mock.create_autospec(GameService(mock_players))
