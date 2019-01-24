import pytest
import time

from aiomysql import DictCursor

from server import db
from server.games import LadderGame
from server.games.game import GameState, ValidityState
from tests.unit_tests.conftest import add_players
from tests.unit_tests.test_game import add_connected_players


@pytest.fixture()
def laddergame(game_service, game_stats_service):
    return LadderGame(465312, game_service, game_stats_service)


async def test_results_ranked_by_victory(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    await laddergame.add_result(players.hosting, 0, 'victory', 1)
    await laddergame.add_result(players.joining, 1, 'defeat', 0)

    assert laddergame.get_army_score(0) == 1
    assert laddergame.get_army_score(1) == 0


async def test_get_army_score_no_results(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    assert laddergame.get_army_score(0) == 0


async def test_is_winner(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    await laddergame.add_result(players.hosting, 0, 'victory', 1)
    await laddergame.add_result(players.joining, 1, 'defeat', 0)

    assert laddergame.is_winner(players.hosting)
    assert laddergame.is_winner(players.joining) is False
    assert laddergame.is_draw is False


async def test_is_winner_on_draw(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    await laddergame.add_result(players.hosting, 0, 'draw', 1)
    await laddergame.add_result(players.joining, 1, 'draw', 1)

    assert laddergame.is_winner(players.hosting) is False
    assert laddergame.is_winner(players.joining) is False
    assert laddergame.is_draw


async def test_rate_game(laddergame: LadderGame, db_pool):
    async with db_pool.get() as conn:
        cursor = await conn.cursor()
        # TODO remove as soon as we have isolated tests (transactions)
        await cursor.execute("DELETE FROM game_stats WHERE id = %s", laddergame.id)
        await cursor.execute("DELETE FROM game_player_stats WHERE gameId = %s", laddergame.id)

    laddergame.state = GameState.LOBBY
    players = add_players(laddergame, 2)
    laddergame.set_player_option(players[0].id, 'Team', 1)
    laddergame.set_player_option(players[1].id, 'Team', 2)
    player_1_old_mean = players[0].ladder_rating[0]
    player_2_old_mean = players[1].ladder_rating[0]

    await laddergame.launch()
    laddergame.launched_at = time.time() - 60*20
    await laddergame.add_result(0, 0, 'victory', 5)
    await laddergame.add_result(0, 1, 'defeat', -5)
    await laddergame.on_game_end()

    assert laddergame.validity is ValidityState.VALID
    assert players[0].ladder_rating[0] > player_1_old_mean
    assert players[1].ladder_rating[0] < player_2_old_mean

    async with db_pool.get() as conn:
        cursor = await conn.cursor(DictCursor)
        await cursor.execute("SELECT mean, deviation, after_mean, after_deviation FROM game_player_stats WHERE gameid = %s", laddergame.id)
        result = await cursor.fetchall()

    assert result[0]['mean'] == 1500
    assert result[0]['deviation'] == 500
    assert result[0]['after_mean'] > result[0]['mean']
    assert result[0]['after_deviation'] < result[0]['deviation']

    assert result[1]['mean'] == 1500
    assert result[1]['deviation'] == 500
    assert result[1]['after_mean'] < result[0]['mean']
    assert result[1]['after_deviation'] < result[0]['deviation']
