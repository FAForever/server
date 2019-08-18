import pytest


@pytest.fixture()
def map_pool():
    return [(1, '', 'scmp_001'), (5, '', 'scmp_05'), (10, '', 'scmp_010'),
            (12, '', 'scmp_012'), (11, '', 'scmp_0011')]


@pytest.fixture()
def player1(lobbythread, player_factory):
    return player_factory(login=f"Player 1", player_id=1,
                          lobby_connection=lobbythread)


@pytest.fixture()
def player2(lobbythread, player_factory):
    return player_factory(login=f"Player 2", player_id=2,
                          lobby_connection=lobbythread)


@pytest.fixture()
def ladder_setup(player1, player2, map_pool):
    return {
        'player1': player1,
        'player2': player2,
        'map_pool': map_pool
    }
