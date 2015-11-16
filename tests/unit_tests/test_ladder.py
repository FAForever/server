from unittest.mock import patch, Mock
import asyncio

from tests.unit_tests.ladder_fixtures import *

def get_coro_mock(return_value):
    @asyncio.coroutine
    def coro_mock(*args, **kwargs):
        return return_value
    return Mock(wraps=coro_mock)

#@asyncio.coroutine
#def test_start_game_uses_map_from_mappool(ladder_service: LadderService, ladder_setup, game_service, lobbythread):
#    game_service.ladder_maps = ladder_setup['map_pool']
#    lobbythread.sendJSON = Mock()
#    yield from ladder_service.start_game(ladder_setup['player1'], ladder_setup['player2'])
#    args, kwargs = lobbythread.sendJSON.call_args
#    assert (args[0]['mapid'], '', args[0]['mapname']) in ladder_setup['map_pool']
