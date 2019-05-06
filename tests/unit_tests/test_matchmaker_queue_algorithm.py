import mock
from server import config
from server.matchmaker import Search, algorithm


def p(mean: int, deviation: int, num_games: int=config.NEWBIE_MIN_GAMES+1, name=None):
    " Make a player with the given ratings"
    player = mock.Mock()
    player.ladder_rating = (mean, deviation)
    player.numGames = num_games
    player.__repr__ = lambda self: name or f"p({self.ladder_rating}, {self.numGames})"
    return player


@mock.patch('server.matchmaker.algorithm.QUEUE_TIME_MOVING_AVG_SIZE', 2)
def test_time_until_next_pop():
    assert algorithm.time_until_next_pop(0) == algorithm.MAX_QUEUE_POP_TIME
    a1 = algorithm.time_until_next_pop(5)
    assert a1 < algorithm.MAX_QUEUE_POP_TIME
    a2 = algorithm.time_until_next_pop(5)
    # Should be strictly less because of the moving average
    assert a2 < a1


def test_rank_all():
    s1 = Search([p(1500, 500, num_games=0)])
    s2 = Search([p(1500, 400, num_games=20)])
    s3 = Search([p(2000, 300, num_games=50)])
    searches = [s1, s2, s3]

    ranks = algorithm._rank_all(searches)

    assert ranks == {
        s1: [s3, s2],
        s2: [s1, s3],
        s3: [s1, s2]
    }


def test_stable_marriage():
    s1 = Search([p(2300, 64, name='p1')])
    s2 = Search([p(1200, 72, name='p2')])
    s3 = Search([p(1300, 175, name='p3')])
    s4 = Search([p(2350, 125, name='p4')])
    s5 = Search([p(1200, 175, name='p5')])
    s6 = Search([p(1250, 175, name='p6')])

    searches = [s1, s2, s3, s4, s5, s6]

    matches = algorithm.stable_marriage(searches)

    assert (s1, s4) in matches
    assert (s2, s5) in matches
    assert (s3, s6) in matches


def test_stable_marriage_better_than_greedy():
    s1 = Search([p(2300, 64, name='p1')])
    s2 = Search([p(2000, 64, name='p2')])
    s3 = Search([p(2100, 64, name='p3')])
    s4 = Search([p(2200, 64, name='p4')])
    s5 = Search([p(2300, 64, name='p5')])
    s6 = Search([p(2400, 64, name='p6')])

    searches = [s1, s2, s3, s4, s5, s6]

    matches = algorithm.stable_marriage(searches)

    # Note that the most ballanced configuration would be
    # assert (s1, s6) in matches  # quality: 0.93
    # assert (s2, s3) in matches  # quality: 0.93
    # assert (s4, s5) in matches  # quality: 0.93

    # However, because s1 is first in the list and gets top choice, we end with
    # the following stable configuration
    assert (s1, s5) in matches  # quality: 0.97
    assert (s2, s3) in matches  # quality: 0.93
    assert (s6, s4) in matches  # quality: 0.82


def test_stable_marriage_unmatch():
    s1 = Search([p(503, 64, name='p1')])
    s2 = Search([p(504, 64, name='p2')])
    s3 = Search([p(504, 64, name='p3')])
    s4 = Search([p(505, 64, name='p4')])

    searches = [s1, s2, s3, s4]

    matches = algorithm.stable_marriage(searches)
    for m1, m2 in matches:
        print(m1, m2, m1.quality_with(m2))

    assert (s1, s4) in matches  # quality: 0.96622
    assert (s2, s3) in matches  # quality: 0.96623
