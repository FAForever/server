from unittest import mock

import pytest

from server.games import CoopGame

pytestmark = pytest.mark.asyncio


async def test_create_coop_game(database):
    game = CoopGame(
        id_=0,
        database=database,
        host=mock.Mock(),
        name="Some game",
        map_="some_map",
        game_mode="coop",
        game_service=mock.Mock(),
        game_stats_service=mock.Mock()
    )
