import pytest
from server.games import LadderGame
from server.games.game import GameState
from tests.unit_tests.test_game import add_connected_players


@pytest.fixture()
def laddergame(game_service, game_stats_service):
    return LadderGame(1, game_service, game_stats_service)


async def test_results_ranked_by_victory(laddergame, players):
    laddergame.state = GameState.LOBBY
    add_connected_players(laddergame, [players.hosting, players.joining])

    await laddergame.add_result(players.hosting, 0, 'victory', 1)
    await laddergame.add_result(players.joining, 1, 'defeat', 0)

    assert laddergame.get_army_score(0) == 1
    assert laddergame.get_army_score(1) == 0
