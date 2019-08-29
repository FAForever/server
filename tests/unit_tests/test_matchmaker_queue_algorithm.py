import mock
from server import config
from server.matchmaker import Search, algorithm


def p(mean: int, deviation: int, ladder_games: int = config.NEWBIE_MIN_GAMES+1, name=None):
    """Make a player with the given ratings"""
    player = mock.Mock()
    player.ladder_rating = (mean, deviation)
    player.ladder_games = ladder_games
    player.__repr__ = lambda self: name or f"p({self.ladder_rating}, {self.ladder_games})"
    return player


def test_rank_all():
    s1 = Search([p(1500, 64, ladder_games=20)])
    s2 = Search([p(1500, 63, ladder_games=20)])
    s3 = Search([p(1600, 75, ladder_games=50)])
    searches = [s1, s2, s3]

    ranks = algorithm._rank_all(searches)

    assert ranks == {
        s1: [s3, s2],
        s2: [s3, s1],
        s3: [s1, s2]
    }


def test_rank_all_will_not_include_matches_below_threshold_quality():
    s1 = Search([p(1500, 500)])
    s2 = Search([p(2000, 300)])
    searches = [s1, s2]

    ranks = algorithm._rank_all(searches)

    assert ranks == {
        s1: [],
        s2: []
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

def test_stable_marriage_matches_new_players_with_new_and_old_with_old():
    new1 = Search([p(1500, 500, name='new1', ladder_games=1)])
    new2 = Search([p(1400, 500, name='new2', ladder_games=2)])
    old1 = Search([p(2300, 75, name='old1', ladder_games=100)])
    old2 = Search([p(2350, 75, name='old2', ladder_games=200)])

    searches = [new1, new2, old1, old2]

    matches = algorithm.stable_marriage(searches)

    assert (new1, new2) in matches
    assert (old1, old2) in matches


def test_stable_marriage_better_than_greedy():
    s1 = Search([p(2300, 64, name='p1')])
    s2 = Search([p(2000, 64, name='p2')])
    s3 = Search([p(2100, 64, name='p3')])
    s4 = Search([p(2200, 64, name='p4')])
    s5 = Search([p(2300, 64, name='p5')])
    s6 = Search([p(2400, 64, name='p6')])

    searches = [s1, s2, s3, s4, s5, s6]

    matches = algorithm.stable_marriage(searches)

    # Note that the most balanced configuration would be
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
