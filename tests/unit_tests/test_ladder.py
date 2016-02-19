from unittest import mock

import pytest

from server import GameStatsService, GameService, LadderService
from server.players import Player
from tests import CoroMock


@pytest.fixture
def ladder_service(game_service: GameService, game_stats_service: GameStatsService):
    return LadderService(game_service, game_stats_service)


async def test_start_game(ladder_service: LadderService, game_service: GameService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p2 = mock.create_autospec(Player('Rhiza', id=2))
    game_service.ladder_maps = [(1, 'scmp_007', 'maps/scmp_007.zip')]

    with mock.patch('asyncio.sleep', CoroMock()):
        await ladder_service.start_game(p1, p2)

    assert p1.lobby_connection.launch_game.called
    assert p2.lobby_connection.launch_game.called


def test_inform_player(ladder_service: LadderService):
    p1 = mock.create_autospec(Player('Dostya', id=1))
    p1.ladder_rating = (1500, 500)

    ladder_service.inform_player(p1)

    assert p1.lobby_connection.sendJSON.called
