import pytest
import time

from sqlalchemy import select, and_
from server.db.models import leaderboard_rating

from server.games import LadderGame
from server.games.game import GameState, ValidityState
from tests.unit_tests.test_game import add_connected_players
from server.rating import RatingType

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def laddergame(database, game_service, game_stats_service, rating_service):
    return LadderGame(
        465312, database, game_service, game_stats_service, rating_service
    )


async def test_results_ranked_by_victory(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    await laddergame.add_result(players.hosting.id, 0, 'victory', 1)
    await laddergame.add_result(players.joining.id, 1, 'defeat', 0)

    assert laddergame.get_army_score(0) == 1
    assert laddergame.get_army_score(1) == 0


async def test_get_army_score_no_results(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    assert laddergame.get_army_score(0) == 0


async def test_get_army_score_returns_0_or_1_only(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    await laddergame.add_result(players.hosting.id, 0, 'victory', 100)
    await laddergame.add_result(players.joining.id, 1, 'defeat', 50)

    assert laddergame.get_army_score(0) == 1


async def test_is_winner(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    await laddergame.add_result(players.hosting.id, 0, 'victory', 1)
    await laddergame.add_result(players.joining.id, 1, 'defeat', 0)

    assert laddergame.is_winner(players.hosting)
    assert not laddergame.is_winner(players.joining)


async def test_is_winner_on_draw(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    await laddergame.add_result(players.hosting.id, 0, 'draw', 1)
    await laddergame.add_result(players.joining.id, 1, 'draw', 1)

    assert not laddergame.is_winner(players.hosting)
    assert not laddergame.is_winner(players.joining)


async def test_rate_game(laddergame: LadderGame, database, game_add_players):
    laddergame.state = GameState.LOBBY
    players = game_add_players(laddergame, 2)
    laddergame.set_player_option(players[0].id, 'Team', 2)
    laddergame.set_player_option(players[1].id, 'Team', 3)
    player_1_old_mean = players[0].ratings[RatingType.LADDER_1V1][0]
    player_2_old_mean = players[1].ratings[RatingType.LADDER_1V1][0]

    await laddergame.launch()
    laddergame.launched_at = time.time() - 60*20
    await laddergame.add_result(0, 0, 'victory', 5)
    await laddergame.add_result(0, 1, 'defeat', -5)
    await laddergame.on_game_end()

    await laddergame.game_service._rating_service._join_rating_queue()

    assert laddergame.validity is ValidityState.VALID
    assert players[0].ratings[RatingType.LADDER_1V1][0] > player_1_old_mean
    assert players[1].ratings[RatingType.LADDER_1V1][0] < player_2_old_mean

    async with database.acquire() as conn:
        result = await conn.execute("SELECT mean, deviation, after_mean, after_deviation FROM game_player_stats WHERE gameid = %s", laddergame.id)
        rows = list(await result.fetchall())

    assert rows[0]['mean'] == 1500
    assert rows[0]['deviation'] == 500
    assert rows[0]['after_mean'] > rows[0]['mean']
    assert rows[0]['after_deviation'] < rows[0]['deviation']

    assert rows[1]['mean'] == 1500
    assert rows[1]['deviation'] == 500
    assert rows[1]['after_mean'] < rows[0]['mean']
    assert rows[1]['after_deviation'] < rows[0]['deviation']


async def test_persist_rating_victory(laddergame: LadderGame, database,
                                      game_add_players):
    laddergame.state = GameState.LOBBY
    players = game_add_players(laddergame, 2)
    laddergame.set_player_option(players[0].id, 'Team', 2)
    laddergame.set_player_option(players[1].id, 'Team', 3)

    rating_sql = select([
        leaderboard_rating.c.total_games,
        leaderboard_rating.c.won_games
    ]).where(
        and_(
            leaderboard_rating.c.login_id.in_((players[0].id, players[1].id)),
            leaderboard_rating.c.leaderboard_id == 2,
        )
    ).order_by(leaderboard_rating.c.login_id)

    async with database.acquire() as conn:
        result = await conn.execute(rating_sql)
        result_before = await result.fetchall()

    await laddergame.launch()
    laddergame.launched_at = time.time() - 60*20
    await laddergame.add_result(0, 0, 'victory', 5)
    await laddergame.add_result(0, 1, 'defeat', -5)
    await laddergame.on_game_end()

    await laddergame.game_service._rating_service._join_rating_queue()

    assert laddergame.validity is ValidityState.VALID

    async with database.acquire() as conn:
        result = await conn.execute(rating_sql)
        result_after = await result.fetchall()

    assert result_after[0]['total_games'] == result_before[0]['total_games'] + 1
    assert result_after[1]['total_games'] == result_before[1]['total_games'] + 1
    assert result_after[0]['won_games'] == result_before[0]['won_games'] + 1
    assert result_after[1]['won_games'] == result_before[1]['won_games']
