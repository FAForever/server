from unittest import mock

from server.games import CoopGame
from server.types import Map


async def test_create_coop_game(database):
    CoopGame(
        id=0,
        database=database,
        host=mock.Mock(),
        name="Some game",
        map=Map(
            id=None,
            folder_name="some_map"
        ),
        game_mode="coop",
        game_service=mock.Mock(),
        game_stats_service=mock.Mock()
    )
