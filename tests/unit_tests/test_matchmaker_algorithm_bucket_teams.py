import math
import random

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from server import config
from server.matchmaker import Search, algorithm
from server.matchmaker.algorithm.bucket_teams import (
    BucketTeamMatchmaker,
    _make_teams,
    _make_teams_from_single
)
from server.rating import RatingType

from .strategies import st_searches_list


@pytest.fixture(scope="module")
def player_factory(player_factory):
    def make(
        mean: int = 1500,
        deviation: int = 500,
        ladder_games: int = config.NEWBIE_MIN_GAMES + 1,
        name=None,
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


@pytest.mark.parametrize("make_teams_func", (_make_teams, _make_teams_from_single))
@given(
    searches=st_searches_list(max_players=1),
    size=st.integers(min_value=1, max_value=10),
)
def test_make_teams_single_correct_size(searches, size, make_teams_func):
    matched, _ = make_teams_func(searches, size)

    assume(matched != [])

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
    matched, non_matched = _make_teams_from_single(searches, size=2)

    assert matched != []
    assert non_matched == []

    for search in matched:
        p1, p2 = search.players
        p1_mean, _ = p1.ratings[RatingType.LADDER_1V1]
        p2_mean, _ = p2.ratings[RatingType.LADDER_1V1]

        assert math.fabs(p1_mean - p2_mean) <= 100


def test_make_teams_single_2v2_small_pool(player_factory):
    """
    When we have a small number of players, we want teams to be formed by
    distributing players of equal skill to different teams so that we can
    maximize the chances of getting a match.
    """

    # Try a bunch of times so it is unlikely to pass by chance
    for _ in range(20):
        searches = [
            Search([player_factory(random.gauss(1000, 5), 10, name=f"p{i}")])
            for i in range(2)
        ]
        searches += [
            Search([player_factory(random.gauss(500, 5), 10, name=f"r{i}")])
            for i in range(2)
        ]
        matched, non_matched = _make_teams_from_single(searches, size=2)

        assert matched != []
        assert non_matched == []

        for search in matched:
            p1, p2 = search.players
            # Order doesn't matter
            if p1.ratings[RatingType.LADDER_1V1][0] > 900:
                assert p2.ratings[RatingType.LADDER_1V1][0] < 600
            else:
                assert p1.ratings[RatingType.LADDER_1V1][0] < 600
                assert p2.ratings[RatingType.LADDER_1V1][0] > 900


def test_make_buckets_performance(bench, player_factory):
    NUM_SEARCHES = 1000
    searches = [
        Search([player_factory(random.gauss(1500, 200), 500, ladder_games=1)])
        for _ in range(NUM_SEARCHES)
    ]

    with bench:
        algorithm.bucket_teams._make_buckets(searches)

    assert bench.elapsed() < 0.15


def test_make_teams_1(player_factory):
    teams = [
        [
            player_factory(name="p1"),
            player_factory(name="p2"),
            player_factory(name="p3"),
        ],
        [player_factory(name="p4"), player_factory(name="p5")],
        [player_factory(name="p6"), player_factory(name="p7")],
        [player_factory(name="p8")],
        [player_factory(name="p9")],
        [player_factory(name="p10")],
        [player_factory(name="p11")],
    ]
    do_test_make_teams(teams, team_size=3, total_unmatched=2, unmatched_sizes={1})


def test_make_teams_2(player_factory):
    teams = [
        [
            player_factory(name="p1"),
            player_factory(name="p2"),
            player_factory(name="p3"),
        ],
        [player_factory(name="p4"), player_factory(name="p5")],
        [player_factory(name="p6"), player_factory(name="p7")],
        [player_factory(name="p8")],
        [player_factory(name="p9")],
        [player_factory(name="p10")],
        [player_factory(name="p11")],
    ]
    do_test_make_teams(teams, team_size=2, total_unmatched=1, unmatched_sizes={3})


def test_make_teams_3(player_factory):
    teams = [[player_factory(name=f"p{i+1}")] for i in range(9)]
    do_test_make_teams(teams, team_size=4, total_unmatched=1, unmatched_sizes={1})


def test_make_teams_4(player_factory):
    teams = [[player_factory()] for i in range(9)]
    teams += [[player_factory(), player_factory()] for i in range(5)]
    teams += [[player_factory(), player_factory(), player_factory()] for i in range(15)]
    teams += [
        [player_factory(), player_factory(), player_factory(), player_factory()]
        for i in range(4)
    ]
    do_test_make_teams(teams, team_size=4, total_unmatched=7, unmatched_sizes={3, 2})


def test_make_teams_5(player_factory):
    teams = [
        [
            player_factory(name="p1"),
            player_factory(name="p2"),
            player_factory(name="p3"),
        ],
        [player_factory(name="p4"), player_factory(name="p5")],
        [player_factory(name="p6"), player_factory(name="p7")],
    ]
    do_test_make_teams(teams, team_size=4, total_unmatched=1, unmatched_sizes={3})


def do_test_make_teams(teams, team_size, total_unmatched, unmatched_sizes):
    searches = [Search(t) for t in teams]

    matched, non_matched = _make_teams(searches, size=team_size)
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

    grouped = [
        search.players for search in algorithm.bucket_teams._distribute(searches, 2)
    ]
    assert grouped == [[p1, p4], [p2, p3]]


def test_distribute_pairs_2(player_factory):
    players = [player_factory(1500, 500, name=f"p{i+1}") for i in range(8)]
    searches = [(Search([player]), 0) for player in players]
    p1, p2, p3, p4, p5, p6, p7, p8 = players

    grouped = [
        search.players for search in algorithm.bucket_teams._distribute(searches, 2)
    ]
    assert grouped == [[p1, p4], [p2, p3], [p5, p8], [p6, p7]]


def test_distribute_triples(player_factory):
    players = [player_factory(1500, 500, name=f"p{i+1}") for i in range(6)]
    searches = [(Search([player]), 0) for player in players]
    p1, p2, p3, p4, p5, p6 = players

    grouped = [
        search.players for search in algorithm.bucket_teams._distribute(searches, 3)
    ]

    assert grouped == [[p1, p3, p6], [p2, p4, p5]]


def test_BucketTeamMatchmaker_1v1(player_factory):
    num_players = 6
    players = [player_factory(1500, 500, name=f"p{i+1}") for i in range(num_players)]
    searches = [Search([player]) for player in players]

    team_size = 1
    matchmaker = BucketTeamMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size)

    assert len(matches) == num_players / 2 / team_size
    assert len(unmatched_searches) == num_players - 2 * team_size * len(matches)


def test_BucketTeamMatchmaker_2v2_single_searches(player_factory):
    num_players = 12
    players = [player_factory(1500, 500, name=f"p{i+1}") for i in range(num_players)]
    searches = [Search([player]) for player in players]

    team_size = 2
    matchmaker = BucketTeamMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size)

    assert len(matches) == num_players / 2 / team_size
    assert len(unmatched_searches) == num_players - 2 * team_size * len(matches)


def test_BucketTeamMatchmaker_2v2_full_party_searches(player_factory):
    num_players = 12
    players = [player_factory(1500, 500, name=f"p{i+1}") for i in range(num_players)]
    searches = [Search([players[i], players[i + 1]]) for i in range(0, len(players), 2)]

    team_size = 2
    matchmaker = BucketTeamMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size)

    assert len(matches) == num_players / 2 / team_size
    assert len(unmatched_searches) == num_players - 2 * team_size * len(matches)


def test_BucketTeammatchmaker_2v2_mixed_party_sizes(player_factory):
    num_players = 24
    players = [player_factory(1500, 500, name=f"p{i+1}") for i in range(num_players)]
    searches = [
        Search([players[i], players[i + 1]]) for i in range(0, len(players) // 2, 2)
    ]
    searches.extend([Search([player]) for player in players[len(players) // 2:]])

    team_size = 2
    matchmaker = BucketTeamMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size)

    assert len(matches) == num_players / 2 / team_size
    assert len(unmatched_searches) == num_players - 2 * team_size * len(matches)


def test_2v2_count_unmatched_searches(player_factory):
    players = [
        player_factory(500, 100, name="lowRating_unmatched_1"),
        player_factory(500, 100, name="lowRating_unmatched_2"),
        player_factory(1500, 100, name="midRating_matched_1"),
        player_factory(1500, 100, name="midRating_matched_2"),
        player_factory(1500, 100, name="midRating_matched_3"),
        player_factory(1500, 100, name="midRating_matched_4"),
        player_factory(2000, 100, name="highRating_unmatched_1"),
    ]
    searches = [Search([player]) for player in players]

    team_size = 2
    matchmaker = BucketTeamMatchmaker()
    matches, unmatched_searches = matchmaker.find(searches, team_size)

    assert len(matches) == 1
    number_of_unmatched_players = sum(
        len(search.players) for search in unmatched_searches
    )
    assert number_of_unmatched_players == 3
