import logging

import pytest
from hypothesis import assume, given, settings

from server import config
from server.matchmaker import Search
from server.matchmaker.algorithm import stable_marriage

from .strategies import st_searches_list


@pytest.fixture(scope="module")
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
            lobby_connection_spec=None,
        )
        return player
    return make


def add_graph_edge_weights(graph) -> stable_marriage.WeightedGraph:
    return {
        s1: [(s2, s1.quality_with(s2)) for s2 in edges]
        for s1, edges in graph.items()
    }


@pytest.mark.parametrize("build_func", (
    stable_marriage._MatchingGraph.build_full,
    stable_marriage._MatchingGraph.build_fast
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
    stable_marriage._MatchingGraph.build_full,
    stable_marriage._MatchingGraph.build_fast
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

    stable_marriage._MatchingGraph.remove_isolated(ranks)

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

    stable_marriage._MatchingGraph.remove_isolated(ranks)

    assert ranks == {}


@pytest.mark.parametrize("build_func", (
    stable_marriage._MatchingGraph.build_full,
    stable_marriage._MatchingGraph.build_fast
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


@pytest.mark.parametrize("build_func", (
    stable_marriage._MatchingGraph.build_full,
    stable_marriage._MatchingGraph.build_fast
))
@given(searches=st_searches_list(max_players=2))
@settings(deadline=300)
def test_matching_graph_symmetric(
    request,
    caplog_context,
    build_func,
    searches
):
    with caplog_context(request) as caplog:
        caplog.set_level(logging.INFO)

        graph = build_func(searches)

        # Verify that any edge also has the reverse edge
        for search, neighbors in graph.items():
            for other, quality in neighbors:
                assert (search, quality) in graph[other]


@pytest.mark.parametrize("build_func", (
    stable_marriage._MatchingGraph.build_full,
    stable_marriage._MatchingGraph.build_fast
))
@given(searches=st_searches_list(max_players=2))
@settings(deadline=300)
def test_stable_marriage_produces_symmetric_matchings(
    request,
    caplog_context,
    build_func,
    searches
):
    with caplog_context(request) as caplog:
        caplog.set_level(logging.INFO)

        ranks = build_func(searches)

        matches = stable_marriage.StableMarriage().find(ranks)

        assume(matches != [])

        for search in matches:
            opponent = matches[search]
            assert matches[opponent] == search


def test_stable_marriage(player_factory):
    s1 = Search([player_factory(2300, 64, name="p1")])
    s2 = Search([player_factory(1200, 72, name="p2")])
    s3 = Search([player_factory(1300, 175, name="p3")])
    s4 = Search([player_factory(2350, 125, name="p4")])
    s5 = Search([player_factory(1200, 175, name="p5")])
    s6 = Search([player_factory(1250, 175, name="p6")])

    searches = [s1, s2, s3, s4, s5, s6]
    ranks = stable_marriage._MatchingGraph.build_full(searches)

    matches = stable_marriage.StableMarriage().find(ranks)

    assert matches[s1] == s4
    assert matches[s2] == s5
    assert matches[s3] == s6


def test_stable_marriage_matches_new_players_with_new_and_old_with_old_if_different_mean(player_factory):
    new1 = Search([player_factory(1500, 500, name="new1", ladder_games=1)])
    new2 = Search([player_factory(1400, 500, name="new2", ladder_games=2)])
    old1 = Search([player_factory(2300, 75, name="old1", ladder_games=100)])
    old2 = Search([player_factory(2350, 75, name="old2", ladder_games=200)])

    searches = [new1, new2, old1, old2]
    ranks = stable_marriage._MatchingGraph.build_full(searches)

    matches = stable_marriage.StableMarriage().find(ranks)

    assert matches[new1] == new2
    assert matches[old1] == old2


def test_stable_marriage_matches_new_players_with_new_and_old_with_old_if_same_mean(player_factory):
    # Assumes that both new players initialized with mean 1500 will be matched
    # as if they had mean 500
    new1 = Search([player_factory(1500, 500, name="new1", ladder_games=0)])
    new2 = Search([player_factory(1500, 500, name="new2", ladder_games=0)])
    old1 = Search([player_factory(500, 75, name="old1", ladder_games=100)])
    old2 = Search([player_factory(500, 75, name="old2", ladder_games=100)])

    searches = [new1, new2, old1, old2]
    ranks = stable_marriage._MatchingGraph.build_full(searches)

    matches = stable_marriage.StableMarriage().find(ranks)

    assert matches[new1] == new2
    assert matches[old1] == old2


def test_newbies_with_big_rating_difference_are_matched_after_failed_matching(player_factory):
    new1 = Search([player_factory(1500, 500, name="new1", ladder_games=0)])
    # this is the lower boundary of the typical rating ranges that people have after 10 games
    new2 = Search([player_factory(100, 160, name="new2", ladder_games=config.NEWBIE_MIN_GAMES)])

    searches = [new1, new2]

    team_size = 1
    matchmaker = stable_marriage.StableMarriageMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size, 1000)

    assert len(matches) == 0
    assert len(unmatched_searches) == 2

    for _ in range(6):
        new1.register_failed_matching_attempt()
        new2.register_failed_matching_attempt()

    matches, unmatched_searches = matchmaker.find(searches, team_size, 1000)

    assert len(matches) == 1
    assert len(unmatched_searches) == 0


def test_newbies_with_big_rating_difference_are_matched_after_failed_matching2(player_factory):
    # keep the rating interpolation in mind
    new1 = Search([player_factory(1500, 500, name="new1", ladder_games=0)])
    # this is the upper boundary of the typical rating ranges that people have after 10 games
    new2 = Search([player_factory(1300, 160, name="new2", ladder_games=config.NEWBIE_MIN_GAMES)])

    searches = [new1, new2]

    team_size = 1
    matchmaker = stable_marriage.StableMarriageMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size, 1000)

    assert len(matches) == 0
    assert len(unmatched_searches) == 2

    for _ in range(6):
        new1.register_failed_matching_attempt()
        new2.register_failed_matching_attempt()

    matches, unmatched_searches = matchmaker.find(searches, team_size, 1000)

    assert len(matches) == 1
    assert len(unmatched_searches) == 0


def test_stable_marriage_does_not_match_new_and_old_players_with_big_rating_difference(player_factory):
    new = Search([player_factory(1500, 500, name="new", ladder_games=0)])
    old = Search([player_factory(1000, 75, name="old", ladder_games=100)])

    searches = [new, old]

    for _ in range(100):
        new.register_failed_matching_attempt()
        old.register_failed_matching_attempt()

    team_size = 1
    matchmaker = stable_marriage.StableMarriageMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size, 1000)

    assert len(matches) == 0
    assert len(unmatched_searches) == 2


def test_newbies_are_matched_with_newbies(player_factory):
    newbie1 = Search([player_factory(0, 500, ladder_games=9)])
    newbie2 = Search([player_factory(750, 500, ladder_games=9)])
    pro = Search([player_factory(1500, 70, ladder_games=100)])

    for _ in range(6):
        newbie1.register_failed_matching_attempt()
        newbie2.register_failed_matching_attempt()
        pro.register_failed_matching_attempt()

    searches = [newbie1, pro, newbie2]
    team_size = 1
    matchmaker = stable_marriage.StableMarriageMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size, 1000)
    match_sets = [set(pair) for pair in matches]

    assert {newbie1, newbie2} in match_sets
    assert unmatched_searches == [pro]


def test_stable_marriage_better_than_greedy(player_factory):
    s1 = Search([player_factory(2300, 64, name="p1")])
    s2 = Search([player_factory(2000, 64, name="p2")])
    s3 = Search([player_factory(2100, 64, name="p3")])
    s4 = Search([player_factory(2200, 64, name="p4")])
    s5 = Search([player_factory(2300, 64, name="p5")])
    s6 = Search([player_factory(2400, 64, name="p6")])

    searches = [s1, s2, s3, s4, s5, s6]
    ranks = stable_marriage._MatchingGraph.build_full(searches)

    matches = stable_marriage.StableMarriage().find(ranks)

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
    s1 = Search([player_factory(503, 64, name="p1")])
    s2 = Search([player_factory(504, 64, name="p2")])
    s3 = Search([player_factory(504, 64, name="p3")])
    s4 = Search([player_factory(505, 64, name="p4")])

    searches = [s1, s2, s3, s4]
    ranks = stable_marriage._MatchingGraph.build_full(searches)

    matches = stable_marriage.StableMarriage().find(ranks)

    assert matches[s1] == s4  # quality: 0.96622
    assert matches[s2] == s3  # quality: 0.96623


def test_matchmaker(player_factory):
    newbie_that_matches1 = Search([player_factory(1450, 500, ladder_games=1)])
    newbie_that_matches2 = Search([player_factory(1550, 500, ladder_games=1)])
    newbie_alone = Search([player_factory(200, 400, ladder_games=9)])

    pro_that_matches1 = Search([player_factory(1800, 60, ladder_games=101)])
    pro_that_matches1.register_failed_matching_attempt()
    pro_that_matches2 = Search([player_factory(1750, 50, ladder_games=100)])
    pro_that_matches2.register_failed_matching_attempt()
    pro_alone = Search([player_factory(1550, 70, ladder_games=100)])
    pro_alone.register_failed_matching_attempt()

    top_player = Search([player_factory(2100, 50, ladder_games=200)])
    top_player.register_failed_matching_attempt()

    searches = [
        newbie_that_matches1,
        newbie_that_matches2,
        newbie_alone,
        pro_that_matches1,
        pro_that_matches2,
        pro_alone,
        top_player
    ]
    team_size = 1
    matchmaker = stable_marriage.StableMarriageMatchmaker()
    match_pairs, unmatched_searches = matchmaker.find(searches, team_size, 1000)
    match_sets = [set(pair) for pair in match_pairs]

    assert {newbie_that_matches1, newbie_that_matches2} in match_sets
    assert {pro_that_matches1, pro_that_matches2} in match_sets
    assert {newbie_alone, pro_alone} not in match_sets
    assert set(unmatched_searches) == {newbie_alone, pro_alone, top_player}
    for match_pair in match_pairs:
        assert newbie_alone not in match_pair
        assert pro_alone not in match_pair
        assert top_player not in match_pair


def test_matchmaker_performance(player_factory, bench, caplog):
    # Disable debug logging for performance
    caplog.set_level(logging.INFO)
    NUM_SEARCHES = 200

    searches = [Search([player_factory(1500, 500, ladder_games=1)]) for _ in range(NUM_SEARCHES)]

    with bench:
        team_size = 1
        matchmaker = stable_marriage.StableMarriageMatchmaker()
        matchmaker.find(searches, team_size, 1000)

    assert bench.elapsed() < 0.5


def test_find_will_not_match_low_quality_games(player_factory):
    s1 = Search([player_factory(1000, 64, name="p1")])
    s2 = Search([player_factory(1300, 64, name="p2")])

    searches = [s1, s2]

    team_size = 1
    matchmaker = stable_marriage.StableMarriageMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size, 1000)

    assert len(matches) == 0
    assert len(unmatched_searches) == len(searches)


def test_unmatched_searches_without_newbies(player_factory):
    players = [
        player_factory(100, 70, name="lowRating_unmatched_1"),
        player_factory(500, 70, name="lowRating_unmatched_2"),
        player_factory(1500, 70, name="midRating_matched_1"),
        player_factory(1500, 70, name="midRating_matched_2"),
        player_factory(1500, 70, name="midRating_matched_3"),
        player_factory(1500, 70, name="midRating_matched_4"),
        player_factory(2000, 70, name="highRating_unmatched_1"),
        player_factory(2500, 70, name="highRating_unmatched_2"),
    ]
    searches = [Search([player]) for player in players]

    team_size = 1
    matchmaker = stable_marriage.StableMarriageMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size, 1000)

    expected_number_of_matches = 2
    assert len(matches) == expected_number_of_matches
    assert len(unmatched_searches) == len(searches) - 2 * team_size * expected_number_of_matches


def test_unmatched_searches_with_newbies(player_factory):
    players = [
        player_factory(100, 70, name="newbie1", ladder_games=1),
        player_factory(200, 70, name="newbie2", ladder_games=1),
        player_factory(300, 70, name="newbie3", ladder_games=1),
        player_factory(400, 70, name="newbie4", ladder_games=1),
        player_factory(500, 70, name="newbie5", ladder_games=1),
        player_factory(750, 70, name="lowRating_unmatched_1"),
        player_factory(1500, 70, name="midRating_matched_1"),
        player_factory(1500, 70, name="midRating_matched_2"),
        player_factory(1500, 70, name="midRating_matched_3"),
        player_factory(1500, 70, name="midRating_matched_4"),
        player_factory(2000, 70, name="highRating_unmatched_1"),
        player_factory(2500, 70, name="highRating_unmatched_2"),
    ]
    searches = [Search([player]) for player in players]

    team_size = 1
    matchmaker = stable_marriage.StableMarriageMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size, 1000)

    expected_number_of_matches = 4
    assert len(matches) == expected_number_of_matches
    assert len(unmatched_searches) == len(searches) - 2 * team_size * expected_number_of_matches
