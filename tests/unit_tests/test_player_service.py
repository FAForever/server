import asyncio
import pytest

from unittest import mock

from server.player_service import PlayerService
from server.players import Player


@pytest.fixture
def player_service(mock_db_pool):
    return mock.create_autospec(PlayerService(mock_db_pool))


@asyncio.coroutine
def test_update_rating(player_service: PlayerService):
    test_player = mock.Mock(spec=Player)
    yield from player_service.update_rating(test_player)

