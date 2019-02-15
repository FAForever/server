import mock
from server.games import CoopGame


def test_create_coop_game():
    game = CoopGame(
        id=0,
        host=mock.Mock(),
        name="Some game",
        map="some_map",
        game_mode='coop',
        game_service=mock.Mock(),
        game_stats_service=mock.Mock()
    )
