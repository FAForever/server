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


def test_stable_marriage_produces_symmetric_matchings():
    s1 = Search([p(2300, 64, name='p1')])
    s2 = Search([p(1200, 72, name='p2')])
    s3 = Search([p(1300, 175, name='p3')])
    s4 = Search([p(2350, 125, name='p4')])
    s5 = Search([p(1200, 175, name='p5')])
    s6 = Search([p(1250, 175, name='p6')])

    searches = [s1, s2, s3, s4, s5, s6]

    matches = algorithm.StableMarriage(searches).find()

    for search in matches:
        opponent = matches[search]
        assert matches[opponent] == search



def test_stable_marriage():
    s1 = Search([p(2300, 64, name='p1')])
    s2 = Search([p(1200, 72, name='p2')])
    s3 = Search([p(1300, 175, name='p3')])
    s4 = Search([p(2350, 125, name='p4')])
    s5 = Search([p(1200, 175, name='p5')])
    s6 = Search([p(1250, 175, name='p6')])

    searches = [s1, s2, s3, s4, s5, s6]

    matches = algorithm.StableMarriage(searches).find()

    assert matches[s1] == s4
    assert matches[s2] == s5
    assert matches[s3] == s6


def test_stable_marriage_matches_new_players_with_new_and_old_with_old_if_different_mean():
    new1 = Search([p(1500, 500, name='new1', ladder_games=1)])
    new2 = Search([p(1400, 500, name='new2', ladder_games=2)])
    old1 = Search([p(2300, 75, name='old1', ladder_games=100)])
    old2 = Search([p(2350, 75, name='old2', ladder_games=200)])

    searches = [new1, new2, old1, old2]

    matches = algorithm.StableMarriage(searches).find()

    assert matches[new1] == new2
    assert matches[old1] == old2


def test_stable_marriage_matches_new_players_with_new_and_old_with_old_if_same_mean():
    # Assumes that both new players initialized with mean 1500 will be matched
    # as if they had mean 500
    new1 = Search([p(1500, 500, name='new1', ladder_games=0)])
    new2 = Search([p(1500, 500, name='new2', ladder_games=0)])
    old1 = Search([p(500, 75, name='old1', ladder_games=100)])
    old2 = Search([p(500, 75, name='old2', ladder_games=100)])

    searches = [new1, new2, old1, old2]

    matches = algorithm.StableMarriage(searches).find()

    assert matches[new1] == new2
    assert matches[old1] == old2


def test_stable_marriage_better_than_greedy():
    s1 = Search([p(2300, 64, name='p1')])
    s2 = Search([p(2000, 64, name='p2')])
    s3 = Search([p(2100, 64, name='p3')])
    s4 = Search([p(2200, 64, name='p4')])
    s5 = Search([p(2300, 64, name='p5')])
    s6 = Search([p(2400, 64, name='p6')])

    searches = [s1, s2, s3, s4, s5, s6]

    matches = algorithm.StableMarriage(searches).find()

    # Note that the most balanced configuration would be
    # (s1, s6)  quality: 0.93
    # (s2, s3)  quality: 0.93
    # (s4, s5)  quality: 0.93

    # However, because s1 is first in the list and gets top choice, we end with
    # the following stable configuration
    assert matches[s1] == s5 # quality: 0.97
    assert matches[s2] == s3 # quality: 0.93
    assert matches[s4] == s6 # quality: 0.82


def test_stable_marriage_unmatch():
    s1 = Search([p(503, 64, name='p1')])
    s2 = Search([p(504, 64, name='p2')])
    s3 = Search([p(504, 64, name='p3')])
    s4 = Search([p(505, 64, name='p4')])

    searches = [s1, s2, s3, s4]

    matches = algorithm.StableMarriage(searches).find()

    assert matches[s1] == s4 # quality: 0.96622
    assert matches[s2] == s3  # quality: 0.96623


def test_random_newbie_matching_is_symmetric():
    s1 = Search([p(1000, 500, name='p1', ladder_games=5)])
    s2 = Search([p(1200, 500, name='p2', ladder_games=5)])
    s3 = Search([p(900, 500, name='p3', ladder_games=5)])
    s4 = Search([p(1500, 500, name='p4', ladder_games=5)])
    s5 = Search([p(1700, 500, name='p5', ladder_games=5)])
    s6 = Search([p(600, 500, name='p6', ladder_games=5)])

    searches = [s1, s2, s3, s4, s5, s6]
    matches = algorithm.RandomlyMatchNewbies(searches).find()

    for search in matches:
        opponent = matches[search]
        assert matches[opponent] == search


def test_newbies_are_forcefully_matched_with_newbies():
    newbie1 = Search([p(0, 500, ladder_games=9)])
    newbie2 = Search([p(1500, 500, ladder_games=9)])
    pro = Search([p(1800, 10, ladder_games=100)])

    searches = [newbie1, pro, newbie2]
    matches = algorithm.RandomlyMatchNewbies(searches).find()

    assert matches[newbie1] == newbie2
    assert matches[newbie2] == newbie1


def test_unmatched_newbies_forcefully_match_pros():
    newbie = Search([p(1500, 500, ladder_games=0)])
    pro = Search([p(1800, 10, ladder_games=100)])

    searches = [newbie, pro]
    matches = algorithm.RandomlyMatchNewbies(searches).find()

    assert len(matches) == 2


def test_unmatched_newbies_do_notforcefully_match_top_players():
    newbie = Search([p(1500, 500, ladder_games=0)])
    top_player = Search([p(2500, 10, ladder_games=100)])

    searches = [newbie, top_player]
    matches = algorithm.RandomlyMatchNewbies(searches).find()

    assert len(matches) == 0


def test_unmatched_newbies_do_not_forcefully_match_teams():
    newbie = Search([p(1500, 500, ladder_games=0)])
    team = Search([p(1500, 100), p(1500, 100)])

    searches = [newbie, team]
    matches = algorithm.RandomlyMatchNewbies(searches).find()

    assert len(matches) == 0


def unmatched_newbie_teams_do_not_forcefully_match_pros():
    newbie_team = Search([
        p(1500, 500, ladder_games=0),
        p(1500, 500, ladder_games=0)
    ])
    pro = Search([p(1800, 10, ladder_games=100)])

    searches = [newbie_team, pro]
    matches = algorithm.RandomlyMatchNewbies(searches).find()

    assert len(matches) == 0


def test_odd_number_of_unmatched_newbies():
    newbie1 = Search([p(-250, 500, ladder_games=9)])
    newbie2 = Search([p(750, 500, ladder_games=9)])
    newbie3 = Search([p(1500, 500, ladder_games=9)])
    pro = Search([p(1800, 10, ladder_games=100)])

    searches = [newbie1, pro, newbie2, newbie3]
    matches = algorithm.RandomlyMatchNewbies(searches).find()

    assert len(matches) == 4

def test_matchmaker():
    newbie_that_matches1 = Search([p(1450, 500, ladder_games=1)])
    newbie_that_matches2 = Search([p(1550, 500, ladder_games=1)])
    newbie_force_matched = Search([p(200, 400, ladder_games=9)])

    pro_that_matches1 = Search([p(1800, 60, ladder_games=101)])
    pro_that_matches2 = Search([p(1750, 50, ladder_games=100)])
    pro_alone = Search([p(1600, 50, ladder_games=100)])

    top_player = Search([p(2100, 50, ladder_games=200)])

    searches = [
        newbie_that_matches1,
        newbie_that_matches2,
        newbie_force_matched,
        pro_that_matches1,
        pro_that_matches2,
        pro_alone,
        top_player
    ]
    match_pairs = algorithm.make_matches(searches)
    match_sets = [set(pair) for pair in match_pairs]

    assert {newbie_that_matches1, newbie_that_matches2} in match_sets
    assert {pro_that_matches1, pro_that_matches2} in match_sets
    assert {newbie_force_matched, pro_alone} in match_sets
    for match_pair in match_pairs:
        assert top_player not in match_pair
