from unittest.mock import patch, Mock
import asyncio

from tests.unit_tests.ladder_fixtures import *

def get_coro_mock(return_value):
    @asyncio.coroutine
    def coro_mock(*args, **kwargs):
        return return_value
    return Mock(wraps=coro_mock)

@asyncio.coroutine
def test_choose_ladder_map_pool_nonempty(container, ladder_setup):
    container.popular_maps = get_coro_mock(return_value=ladder_setup['popular_maps'])
    container.selected_maps = get_coro_mock(return_value=ladder_setup['player1_maps'])
    pool = yield from container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])

    assert len(pool) > 0


@asyncio.coroutine
def test_choose_ladder_map_pool_selects_from_p1_and_popular(container, ladder_setup):
    with patch('random.choice', lambda s: ladder_setup['player1_maps']):
        container.popular_maps = get_coro_mock(return_value=ladder_setup['popular_maps'])
        container.selected_maps = get_coro_mock(return_value=ladder_setup['player1_maps'])

        expected_map_pool = ladder_setup['player1_maps'] & ladder_setup['player2_maps']
        expected_map_pool |= ladder_setup['player1_maps'] | ladder_setup['popular_maps']

        actual_pool = yield from container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])
        assert expected_map_pool == actual_pool


@asyncio.coroutine
def test_choose_ladder_map_pool_selects_from_p2_and_popular(container, ladder_setup):
    with patch('random.choice', lambda s: ladder_setup['player2_maps']):
        container.popular_maps = get_coro_mock(return_value=ladder_setup['popular_maps'])
        container.selected_maps = get_coro_mock(return_value=ladder_setup['player2_maps'])

        expected_map_pool = ladder_setup['player2_maps'] | ladder_setup['popular_maps']

        actual_pool = yield from container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])
        assert expected_map_pool == actual_pool

@asyncio.coroutine
def test_starts_game_with_map_from_popular(container, ladder_setup):
    with patch('random.choice', lambda s: ladder_setup['popular_maps']):
        container.popular_maps = get_coro_mock(return_value=ladder_setup['popular_maps'])

        expected_map_pool = ladder_setup['popular_maps']
        expected_map_pool |= ladder_setup['player1_maps'] & ladder_setup['player2_maps']

        actual_pool = yield from container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])
        assert expected_map_pool == actual_pool


@asyncio.coroutine
def test_choose_ladder_map_pool_previous_games(container: Ladder1V1GamesContainer, ladder_setup, lobbythread):
    container.get_recent_maps = get_coro_mock(return_value=ladder_setup['recently_played'])
    container.selected_maps = get_coro_mock(return_value=ladder_setup['player1_maps'])
    pool = yield from container.choose_ladder_map_pool(ladder_setup['player1'], ladder_setup['player2'])

    recent = container.get_recent_maps([ladder_setup['player1'], ladder_setup['player2']])
    assert pool.isdisjoint(recent)


@asyncio.coroutine
def test_start_game_uses_map_from_mappool(container: Ladder1V1GamesContainer, ladder_setup, lobbythread):
    map_pool = ladder_setup['popular_maps']
    container.choose_ladder_map_pool = get_coro_mock(return_value=map_pool)
    lobbythread.sendJSON = Mock()
    container.getMapName = get_coro_mock(1)
    yield from container.startGame(ladder_setup['player1'], ladder_setup['player2'])
    args, kwargs = lobbythread.sendJSON.call_args
    assert int(args[0]['mapname']) in map_pool


@asyncio.coroutine
def test_keeps_track_of_started_games(container, ladder_setup):
    map_pool = ladder_setup['popular_maps']
    container.choose_ladder_map_pool = get_coro_mock(return_value=map_pool)

    yield from container.startGame(ladder_setup['player1'], ladder_setup['player2'])
    assert len(container.games) == 1
