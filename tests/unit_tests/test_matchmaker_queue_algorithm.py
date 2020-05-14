import logging
import math
import random

import pytest

from hypothesis import given, settings
from hypothesis import strategies as st

from server import config
from server.matchmaker import Search, algorithm
from server.rating import RatingType
from tests.conftest import make_player


@st.composite
def st_players(draw, name="Player"):
    """Strategy for generating Player objects"""
    return make_player(
        ladder_rating=(draw(st.floats(0, 2500)), draw(st.floats(1, 500))),
        ladder_games=draw(st.integers(0, 1000)),
        login=name
    )


@st.composite
def st_searches(draw, num_players=1):
    """Strategy for generating Search objects"""
    return Search([
        draw(st_players(f"p{i}")) for i in range(num_players)
    ])


@st.composite
def st_searches_list(draw, min_players=1, max_players=10, max_size=30):
    """Strategy for generating a list of Search objects"""
    return draw(
        st.lists(
            st_searches(
                num_players=draw(
                    st.integers(min_value=min_players, max_value=max_players)
                )
            ),
            max_size=max_size
        )
    )


@pytest.fixture(scope="session")
def player_factory(player_factory):
    def make(
        mean: int = 1500,
        deviation: int = 500,
        ladder_games: int = config.NEWBIE_MIN_GAMES+1,
        name=None
    ):
        """Make a player with the given ratings"""
        player = player_factory(
            ladder_rating=(mean, deviation),
            ladder_games=ladder_games,
            login=name,
            with_lobby_connection=False,
        )
        return player
    return make


def add_graph_edge_weights(graph) -> algorithm.WeightedGraph:
    return {
        s1: [(s2, s1.quality_with(s2)) for s2 in edges]
        for s1, edges in graph.items()
    }


@pytest.mark.parametrize("build_func", (
    algorithm._MatchingGraph.build_full,
    algorithm._MatchingGraph.build_fast
))
def test_build_full_matching_graph(player_factory, build_func):
    # For small numbers of searches, build_full and build_fast should create
    # the same graph
    s1 = Search([player_factory(1500, 64, ladder_games=20)])
    s2 = Search([player_factory(1500, 63, ladder_games=20)])
    s3 = Search([player_factory(1600, 75, ladder_games=50)])
    searches = [s1, s2, s3]

    ranks = build_func(searches)

    assert ranks == add_graph_edge_weights({
        s1: [s3, s2],
        s2: [s3, s1],
        s3: [s1, s2]
    })


@pytest.mark.parametrize("build_func", (
    algorithm._MatchingGraph.build_full,
    algorithm._MatchingGraph.build_fast
))
def test_build_matching_graph_different_ranks(player_factory, build_func):
    s1 = Search([player_factory(1500, 64, ladder_games=20)])
    s2 = Search([player_factory(200, 63, ladder_games=20)])
    searches = [s1, s2]

    ranks = build_func(searches)

    empty_graph = add_graph_edge_weights({
        s1: [],
        s2: [],
    })

    assert ranks == empty_graph


def test_remove_isolated(player_factory):
    s1 = Search([player_factory(1500, 64, ladder_games=20)])
    s2 = Search([player_factory(1500, 63, ladder_games=20)])
    s3 = Search([player_factory(1600, 75, ladder_games=50)])
    ranks = add_graph_edge_weights({
        s1: [s3],
        s2: [],
        s3: [s1]
    })

    algorithm._MatchingGraph.remove_isolated(ranks)

    assert ranks == add_graph_edge_weights({
        s1: [s3],
        s3: [s1]
    })


def test_remove_isolated_2(player_factory):
    s1 = Search([player_factory(1500, 64, ladder_games=20)])
    s2 = Search([player_factory(1500, 63, ladder_games=20)])
    s3 = Search([player_factory(1600, 75, ladder_games=50)])
    ranks = {
        s1: [],
        s2: [],
        s3: []
    }

    algorithm._MatchingGraph.remove_isolated(ranks)

    assert ranks == {}


@pytest.mark.parametrize("build_func", (
    algorithm._MatchingGraph.build_full,
    algorithm._MatchingGraph.build_fast
))
def test_match_graph_will_not_include_matches_below_threshold_quality(player_factory, build_func):
    s1 = Search([player_factory(1500, 500)])
    s2 = Search([player_factory(2000, 300)])
    searches = [s1, s2]

    ranks = build_func(searches)

    assert ranks == {
        s1: [],
        s2: []
    }


# https://github.com/HypothesisWorks/hypothesis/issues/377
@pytest.mark.filterwarnings("ignore:.*'caplog' fixture")
@pytest.mark.parametrize("build_func", (
    algorithm._MatchingGraph.build_full,
    algorithm._MatchingGraph.build_fast
))
@given(searches=st_searches_list(max_players=2))
@settings(deadline=300)
def test_matching_graph_symmetric(caplog, build_func, searches):
    caplog.set_level(logging.INFO)

    graph = build_func(searches)

    # Verify that any edge also has the reverse edge
    for search, neighbors in graph.items():
        for other, quality in neighbors:
            assert (search, quality) in graph[other]


# https://github.com/HypothesisWorks/hypothesis/issues/377
@pytest.mark.filterwarnings("ignore:.*'caplog' fixture")
@pytest.mark.parametrize("build_func", (
    algorithm._MatchingGraph.build_full,
    algorithm._MatchingGraph.build_fast
))
@given(searches=st_searches_list(max_players=2))
@settings(deadline=300)
def test_stable_marriage_produces_symmetric_matchings(caplog, build_func, searches):
    caplog.set_level(logging.INFO)

    ranks = build_func(searches)

    matches = algorithm.StableMarriage().find(ranks)

    for search in matches:
        opponent = matches[search]
        assert matches[opponent] == search


def test_stable_marriage(player_factory):
    s1 = Search([player_factory(2300, 64, name='p1')])
    s2 = Search([player_factory(1200, 72, name='p2')])
    s3 = Search([player_factory(1300, 175, name='p3')])
    s4 = Search([player_factory(2350, 125, name='p4')])
    s5 = Search([player_factory(1200, 175, name='p5')])
    s6 = Search([player_factory(1250, 175, name='p6')])

    searches = [s1, s2, s3, s4, s5, s6]
    ranks = algorithm._MatchingGraph.build_full(searches)

    matches = algorithm.StableMarriage().find(ranks)

    assert matches[s1] == s4
    assert matches[s2] == s5
    assert matches[s3] == s6


def test_stable_marriage_matches_new_players_with_new_and_old_with_old_if_different_mean(player_factory):
    new1 = Search([player_factory(1500, 500, name='new1', ladder_games=1)])
    new2 = Search([player_factory(1400, 500, name='new2', ladder_games=2)])
    old1 = Search([player_factory(2300, 75, name='old1', ladder_games=100)])
    old2 = Search([player_factory(2350, 75, name='old2', ladder_games=200)])

    searches = [new1, new2, old1, old2]
    ranks = algorithm._MatchingGraph.build_full(searches)

    matches = algorithm.StableMarriage().find(ranks)

    assert matches[new1] == new2
    assert matches[old1] == old2


def test_stable_marriage_matches_new_players_with_new_and_old_with_old_if_same_mean(player_factory):
    # Assumes that both new players initialized with mean 1500 will be matched
    # as if they had mean 500
    new1 = Search([player_factory(1500, 500, name='new1', ladder_games=0)])
    new2 = Search([player_factory(1500, 500, name='new2', ladder_games=0)])
    old1 = Search([player_factory(500, 75, name='old1', ladder_games=100)])
    old2 = Search([player_factory(500, 75, name='old2', ladder_games=100)])

    searches = [new1, new2, old1, old2]
    ranks = algorithm._MatchingGraph.build_full(searches)

    matches = algorithm.StableMarriage().find(ranks)

    assert matches[new1] == new2
    assert matches[old1] == old2


def test_stable_marriage_better_than_greedy(player_factory):
    s1 = Search([player_factory(2300, 64, name='p1')])
    s2 = Search([player_factory(2000, 64, name='p2')])
    s3 = Search([player_factory(2100, 64, name='p3')])
    s4 = Search([player_factory(2200, 64, name='p4')])
    s5 = Search([player_factory(2300, 64, name='p5')])
    s6 = Search([player_factory(2400, 64, name='p6')])

    searches = [s1, s2, s3, s4, s5, s6]
    ranks = algorithm._MatchingGraph.build_full(searches)

    matches = algorithm.StableMarriage().find(ranks)

    # Note that the most balanced configuration would be
    # (s1, s6)  quality: 0.93
    # (s2, s3)  quality: 0.93
    # (s4, s5)  quality: 0.93

    # However, because s1 is first in the list and gets top choice, we end with
    # the following stable configuration
    assert matches[s1] == s5  # quality: 0.97
    assert matches[s2] == s3  # quality: 0.93
    assert matches[s4] == s6  # quality: 0.82


def test_stable_marriage_unmatch(player_factory):
    s1 = Search([player_factory(503, 64, name='p1')])
    s2 = Search([player_factory(504, 64, name='p2')])
    s3 = Search([player_factory(504, 64, name='p3')])
    s4 = Search([player_factory(505, 64, name='p4')])

    searches = [s1, s2, s3, s4]
    ranks = algorithm._MatchingGraph.build_full(searches)

    matches = algorithm.StableMarriage().find(ranks)

    assert matches[s1] == s4  # quality: 0.96622
    assert matches[s2] == s3  # quality: 0.96623


def test_random_newbie_matching_is_symmetric(player_factory):
    s1 = Search([player_factory(1000, 500, name='p1', ladder_games=5)])
    s2 = Search([player_factory(1200, 500, name='p2', ladder_games=5)])
    s3 = Search([player_factory(900, 500, name='p3', ladder_games=5)])
    s4 = Search([player_factory(1500, 500, name='p4', ladder_games=5)])
    s5 = Search([player_factory(1700, 500, name='p5', ladder_games=5)])
    s6 = Search([player_factory(600, 500, name='p6', ladder_games=5)])

    searches = [s1, s2, s3, s4, s5, s6]
    matches = algorithm.RandomlyMatchNewbies().find(searches)

    for search in matches:
        opponent = matches[search]
        assert matches[opponent] == search


def test_newbies_are_forcefully_matched_with_newbies(player_factory):
    newbie1 = Search([player_factory(0, 500, ladder_games=9)])
    newbie2 = Search([player_factory(1500, 500, ladder_games=9)])
    pro = Search([player_factory(1500, 10, ladder_games=100)])

    searches = [newbie1, pro, newbie2]
    matches = algorithm.RandomlyMatchNewbies().find(searches)

    assert matches[newbie1] == newbie2
    assert matches[newbie2] == newbie1


def test_unmatched_newbies_forcefully_match_pros(player_factory):
    newbie = Search([player_factory(1500, 500, ladder_games=0)])
    pro = Search([player_factory(1400, 10, ladder_games=100)])

    searches = [newbie, pro]
    matches = algorithm.RandomlyMatchNewbies().find(searches)

    assert len(matches) == 2


def test_unmatched_newbies_do_notforcefully_match_top_players(player_factory):
    newbie = Search([player_factory(1500, 500, ladder_games=0)])
    top_player = Search([player_factory(2500, 10, ladder_games=100)])

    searches = [newbie, top_player]
    matches = algorithm.RandomlyMatchNewbies().find(searches)

    assert len(matches) == 0


def test_unmatched_newbies_do_not_forcefully_match_teams(player_factory):
    newbie = Search([player_factory(1500, 500, ladder_games=0)])
    team = Search([player_factory(1500, 100), player_factory(1500, 100)])

    searches = [newbie, team]
    matches = algorithm.RandomlyMatchNewbies().find(searches)

    assert len(matches) == 0


def unmatched_newbie_teams_do_not_forcefully_match_pros(player_factory):
    newbie_team = Search([
        player_factory(1500, 500, ladder_games=0),
        player_factory(1500, 500, ladder_games=0)
    ])
    pro = Search([player_factory(1800, 10, ladder_games=100)])

    searches = [newbie_team, pro]
    matches = algorithm.RandomlyMatchNewbies().find(searches)

    assert len(matches) == 0


def test_odd_number_of_unmatched_newbies(player_factory):
    newbie1 = Search([player_factory(-250, 500, ladder_games=9)])
    newbie2 = Search([player_factory(750, 500, ladder_games=9)])
    newbie3 = Search([player_factory(1500, 500, ladder_games=9)])
    pro = Search([player_factory(1500, 10, ladder_games=100)])

    searches = [newbie1, pro, newbie2, newbie3]
    matches = algorithm.RandomlyMatchNewbies().find(searches)

    assert len(matches) == 4


def test_matchmaker(player_factory):
    newbie_that_matches1 = Search([player_factory(1450, 500, ladder_games=1)])
    newbie_that_matches2 = Search([player_factory(1550, 500, ladder_games=1)])
    newbie_force_matched = Search([player_factory(200, 400, ladder_games=9)])

    pro_that_matches1 = Search([player_factory(1800, 60, ladder_games=101)])
    pro_that_matches2 = Search([player_factory(1750, 50, ladder_games=100)])
    pro_alone = Search([player_factory(1550, 50, ladder_games=100)])

    top_player = Search([player_factory(2100, 50, ladder_games=200)])

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


def test_matchmaker_performance(player_factory, bench, caplog):
    # Disable debug logging for performance
    caplog.set_level(logging.INFO)
    NUM_SEARCHES = 200

    searches = [Search([player_factory(1500, 500, ladder_games=1)]) for _ in range(NUM_SEARCHES)]

    with bench:
        algorithm.make_matches(searches)

    assert bench.elapsed() < 0.5


def test_matchmaker_random_only(player_factory):
    newbie1 = Search([player_factory(1550, 500, ladder_games=1)])
    newbie2 = Search([player_factory(200, 400, ladder_games=9)])

    searches = (newbie1, newbie2)
    match_pairs = algorithm.make_matches(searches)
    match_sets = [set(pair) for pair in match_pairs]

    assert {newbie1, newbie2} in match_sets


def test_make_matches_will_not_match_low_quality_games(player_factory):
    s1 = Search([player_factory(100, 64, name='p1')])
    s2 = Search([player_factory(2000, 64, name='p2')])

    searches = [s1, s2]

    matches = algorithm.make_matches(searches)

    assert (s1, s2) not in matches
    assert (s2, s1) not in matches


def test_make_matches_communicates_failed_attempts(player_factory):
    s1 = Search([player_factory(100, 64, name='p1')])
    s2 = Search([player_factory(2000, 64, name='p2')])

    searches = [s1, s2]

    assert s1.failed_matching_attempts == 0
    assert s2.failed_matching_attempts == 0

    matches = algorithm.make_matches(searches)

    # These searches should not have been matched
    assert not matches
    assert s1.failed_matching_attempts == 1
    assert s2.failed_matching_attempts == 1


@pytest.mark.parametrize("make_teams_func", (
    algorithm.make_teams,
    algorithm.make_teams_from_single
))
@given(
    searches=st_searches_list(max_players=1),
    size=st.integers(min_value=1, max_value=10)
)
def test_make_teams_single_correct_size(searches, size, make_teams_func):
    matched, non_matched = make_teams_func(searches, size)

    for search in matched:
        assert len(search.players) == size


def test_make_teams_single_2v2_large_pool(player_factory):
    """
    When we have a large number of players all with similar ratings, we want
    teams to be formed by putting players with the same rating on the same team.
    """

    # Large enough so the test is unlikely to pass by chance
    num = 40

    searches = [
        Search([player_factory(random.uniform(950, 1050), 10, name=f"p{i}")])
        for i in range(num)
    ]
    searches += [
        Search([player_factory(random.uniform(450, 550), 10, name=f"p{i}")])
        for i in range(num)
    ]
    matched, non_matched = algorithm.make_teams_from_single(searches, size=2)

    assert matched != []
    assert non_matched == []

    for search in matched:
        p1, p2 = search.players
        p1_mean, _ = p1.ratings[RatingType.LADDER_1V1]
        p2_mean, _ = p2.ratings[RatingType.LADDER_1V1]
        #
        assert math.fabs(p1_mean - p2_mean) <= 100


def test_make_teams_single_2v2_small_pool(player_factory):
    """
    When we have a small number of players, we want teams to be formed by
    distributing players of equal skill to different teams so that we can
    maximize the chances of getting a match.
    """

    # Try a bunch of times so it is unlikely to pass by chance
    for _ in range(20):
        searches = [Search([player_factory(1000, 10, name=f"p{i}")]) for i in range(2)]
        searches += [Search([player_factory(500, 10, name=f"r{i}")]) for i in range(2)]
        matched, non_matched = algorithm.make_teams_from_single(searches, size=2)

        assert matched != []
        assert non_matched == []

        for search in matched:
            p1, p2 = search.players
            # Order doesn't matter
            if p1.ratings[RatingType.LADDER_1V1] == (1000, 10):
                assert p2.ratings[RatingType.LADDER_1V1] == (500, 10)
            else:
                assert p1.ratings[RatingType.LADDER_1V1] == (500, 10)
                assert p2.ratings[RatingType.LADDER_1V1] == (1000, 10)


def test_make_buckets_performance(bench, player_factory):
    NUM_SEARCHES = 1000
    searches = [
        Search([player_factory(
            random.gauss(1500, 200),
            500,
            ladder_games=1
        )])
        for _ in range(NUM_SEARCHES)
    ]

    with bench:
        algorithm._make_buckets(searches)

    assert bench.elapsed() < 0.1


def test_make_teams_1(player_factory):
    teams = [
        [player_factory(name="p1"), player_factory(name="p2"), player_factory(name="p3")],
        [player_factory(name="p4"), player_factory(name="p5")],
        [player_factory(name="p6"), player_factory(name="p7")],
        [player_factory(name="p8")],
        [player_factory(name="p9")],
        [player_factory(name="p10")],
        [player_factory(name="p11")]
    ]
    do_test_make_teams(teams, 3, 2, {1})


def test_make_teams_2(player_factory):
    teams = [
        [player_factory(name="p1"), player_factory(name="p2"), player_factory(name="p3")],
        [player_factory(name="p4"), player_factory(name="p5")],
        [player_factory(name="p6"), player_factory(name="p7")],
        [player_factory(name="p8")],
        [player_factory(name="p9")],
        [player_factory(name="p10")],
        [player_factory(name="p11")]
    ]
    do_test_make_teams(teams, 2, 1, {3})


def test_make_teams_3(player_factory):
    teams = [
        [player_factory(name=f"p{i+1}")] for i in range(9)
    ]
    do_test_make_teams(teams, 4, 1, {1})


def test_make_teams_4(player_factory):
    teams = [[player_factory()] for i in range(9)]
    teams += [[player_factory(), player_factory()] for i in range(5)]
    teams += [[player_factory(), player_factory(), player_factory()] for i in range(15)]
    teams += [[player_factory(), player_factory(), player_factory(), player_factory()] for i in range(4)]
    do_test_make_teams(teams, 4, 7, {3, 2})


def test_make_teams_5(player_factory):
    teams = [
        [player_factory(name="p1"), player_factory(name="p2"), player_factory(name="p3")],
        [player_factory(name="p4"), player_factory(name="p5")],
        [player_factory(name="p6"), player_factory(name="p7")],
    ]
    do_test_make_teams(teams, 4, 1, {3})


def do_test_make_teams(teams, team_size, total_unmatched, unmatched_sizes):
    searches = [Search(t) for t in teams]

    matched, non_matched = algorithm.make_teams(searches, size=team_size)
    players_non_matched = [s.players for s in non_matched]

    for s in matched:
        assert len(s.players) == team_size
    assert len(players_non_matched) == total_unmatched
    for players in players_non_matched:
        assert len(players) in unmatched_sizes


def test_distribute_pairs_1(player_factory):
    players = [player_factory(1500, 500, name=f"p{i+1}") for i in range(4)]
    searches = [(Search([player]), 0) for player in players]
    p1, p2, p3, p4 = players

    grouped = [search.players for search in algorithm._distribute(searches, 2)]
    assert grouped == [[p1, p4], [p2, p3]]


def test_distribute_pairs_2(player_factory):
    players = [player_factory(1500, 500, name=f"p{i+1}") for i in range(8)]
    searches = [(Search([player]), 0) for player in players]
    p1, p2, p3, p4, p5, p6, p7, p8 = players

    grouped = [search.players for search in algorithm._distribute(searches, 2)]
    assert grouped == [[p1, p4], [p2, p3], [p5, p8], [p6, p7]]


def test_distribute_triples(player_factory):
    players = [player_factory(1500, 500, name=f"p{i+1}") for i in range(6)]
    searches = [(Search([player]), 0) for player in players]
    p1, p2, p3, p4, p5, p6 = players

    grouped = [search.players for search in algorithm._distribute(searches, 3)]

    assert grouped == [[p1, p3, p6], [p2, p4, p5]]
