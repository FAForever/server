from unittest.mock import patch, Mock
import asyncio

from tests.unit_tests.ladder_fixtures import *

def get_coro_mock(return_value):
    @asyncio.coroutine
    def coro_mock(*args, **kwargs):
        return return_value
    return Mock(wraps=coro_mock)

@asyncio.coroutine
def test_start_game_uses_map_from_mappool(container: Ladder1V1GamesContainer, ladder_setup, game_service, lobbythread):
    game_service.ladder_maps = ladder_setup['map_pool']
    lobbythread.sendJSON = Mock()
    yield from container.startGame(ladder_setup['player1'], ladder_setup['player2'])
    args, kwargs = lobbythread.sendJSON.call_args
    assert int(args[0]['mapname']) in map_pool

@asyncio.coroutine
def test_keeps_track_of_started_games(container, ladder_setup, game_service):
    game_service.ladder_maps = ladder_setup['map_pool']

    yield from container.startGame(ladder_setup['player1'], ladder_setup['player2'])
    assert len(container.games) == 1
