import pytest

from unittest import mock

from server.player_service import PlayerService

@pytest.fixture
def player_service(mock_db_pool):
    return mock.create_autospec(PlayerService(mock_db_pool))
