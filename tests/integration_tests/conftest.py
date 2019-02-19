from unittest import mock

import pytest


@pytest.fixture
def mock_players(db_engine):
    from server import PlayerService
    m = mock.create_autospec(PlayerService())
    m.client_version_info = (0, None)
    return m

@pytest.fixture
def mock_games(mock_players):
    from server import GameService
    return mock.create_autospec(GameService(mock_players))
