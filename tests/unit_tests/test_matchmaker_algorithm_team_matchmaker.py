import logging
import random
import statistics
import numpy
import matplotlib.pyplot as plt

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from matplotlib.ticker import MultipleLocator
from sortedcontainers import SortedList

from server import config
from server.matchmaker import CombinedSearch, Search
from server.matchmaker.algorithm.team_matchmaker import (
    NotEnoughPlayersException,
    TeamMatchMaker,
    UnevenTeamsException
)
from server.matchmaker.search import Match

from .strategies import (
    st_game_candidates_list,
    st_players,
    st_searches,
    st_searches_list,
    st_searches_list_with_index,
    st_searches_list_with_player_size
)


@pytest.fixture(scope="module")
def player_factory(player_factory):
    player_id_counter = 0

    def make(
        mean: int = 1500,
        deviation: int = 500,
        ladder_games: int = config.NEWBIE_MIN_GAMES+1,
        name=None
    ):
        """Make a player with the given ratings"""
        nonlocal player_id_counter
        player = player_factory(
            ladder_rating=(mean, deviation),
            ladder_games=ladder_games,
            login=name,
            lobby_connection_spec=None,
            player_id=player_id_counter
        )
        player_id_counter += 1
        return player
    return make


def make_searches(ratings, player_factory):
    return [Search([player_factory(r + 300, 100, name=f"p{i}")]) for i, r in enumerate(ratings)]


def calculate_game_quality(match: Match) -> float:
    ratings = []
    for team in match:
        for search in team.get_original_searches():
            ratings.append(search.average_rating)

    rating_disparity = abs(match[0].cumulative_rating - match[1].cumulative_rating)
    fairness = max((config.MAXIMUM_RATING_IMBALANCE - rating_disparity) / config.MAXIMUM_RATING_IMBALANCE, 0)
    deviation = statistics.pstdev(ratings)
    uniformity = max((config.MAXIMUM_RATING_DEVIATION - deviation) / config.MAXIMUM_RATING_DEVIATION, 0)

    quality = fairness * uniformity
    return quality


def get_random_searches_list(player_factory, min_size=0, max_size=10, max_players=4):
    searches = []
    for _ in range(random.randint(min_size, max_size)):
        # With this distribution the number of players is 1.4 * len(list)
        num_players = min(int(random.paretovariate(2.0)), max_players)
        players = [player_factory(
            mean=int(random.triangular(-200, 2200, 900)),
            deviation=int(random.triangular(10, 200, 80)),
            ladder_games=random.randint(0, 200),
            name=f"p{i}"
        ) for i in range(num_players)]
        searches.append(Search(players))

    return searches


def test_matchmaker(caplog, player_factory):
    # Disable debug logging for performance
    caplog.set_level(logging.INFO)

    matchmaker = TeamMatchMaker()
    qualities = []
    queue_len_before_pop = []
    created_games = []
    queue_len_after_pop = []
    wait_time = SortedList()
    newbie_wait_time = []
    queue = []
    iteration = []
    for i in range(500):
        queue.extend(get_random_searches_list(player_factory, 0, 4, 4))
        queue_len_before_pop.append(sum(len(search.players) for search in queue))

        matches, unmatched = matchmaker.find(queue, 4)

        created_games.append(len(matches))
        queue_len_after_pop.append(sum(len(search.players) for search in unmatched))
        for search in unmatched:
            search.register_failed_matching_attempt()
        for match in matches:
            quality_without_bonuses = calculate_game_quality(match)
            qualities.append(quality_without_bonuses)
            if i % 10 == 0:
                print(f"{repr(match[0].get_original_searches())} tot. rating: {match[0].cumulative_rating} vs "
                      f"{repr(match[1].get_original_searches())} tot. rating: {match[1].cumulative_rating} "
                      f"Quality: {quality_without_bonuses}")
            wait_time.update(search.failed_matching_attempts
                             for team in match for search in team.get_original_searches())
            newbie_wait_time.extend(search.failed_matching_attempts
                                    for team in match for search in team.get_original_searches() if search.has_newbie())
        queue = unmatched
        iteration.append(i)

    wait_time_90_percentile = numpy.percentile(wait_time, 90)
    max_wait_time = wait_time.pop()
    avg_wait_time = statistics.mean(wait_time)
    med_wait_time = statistics.median(wait_time)
    newbie_wait_time_90_percentile = numpy.percentile(newbie_wait_time, 90)
    newbie_max_wait_time = max(newbie_wait_time)
    newbie_avg_wait_time = statistics.mean(newbie_wait_time)
    newbie_med_wait_time = statistics.median(newbie_wait_time)
    min_length = min(queue_len_after_pop)
    max_length = max(queue_len_after_pop)
    avg_length = statistics.mean(queue_len_after_pop)
    med_length = statistics.median(queue_len_after_pop)
    best_quality = max(qualities)
    worst_quality = min(qualities)
    avg_quality = statistics.mean(qualities)
    quality_percentile = numpy.percentile(qualities, 75)

    print()
    print(f"quality was between {worst_quality} and {best_quality} "
          f"with average {avg_quality} and 75th percentile {quality_percentile}")
    print(f"number of unmatched players was between {min_length} and {max_length} "
          f"with average {avg_length} and median {med_length}")
    print(f"matched {len(wait_time)} searches total")
    #print(wait_time)
    print(f"wait time was on average {avg_wait_time}, median {med_wait_time}, "
          f"90th percentile {wait_time_90_percentile} and max {max_wait_time} cycles")
    print(f"matched {len(newbie_wait_time)} newbie searches")
    print(f"newbie wait time was on average {newbie_avg_wait_time}, median {newbie_med_wait_time}, "
          f"90th percentile {newbie_wait_time_90_percentile} and max {newbie_max_wait_time} cycles")

    fig, ax = plt.subplots()
    ax.plot(iteration, queue_len_before_pop, label='length before pop')
    ax.plot(iteration, created_games, label='created games')
    ax.plot(iteration, queue_len_after_pop, label='length after pop')
    ax.grid()
    ax.legend()
    ax.yaxis.set_major_locator(MultipleLocator(4))
    plt.show()


def test_player_generation(player_factory):
    searches = get_random_searches_list(player_factory, min_size=1000, max_size=1000, max_players=4)
    searches_by_size = TeamMatchMaker()._searches_by_size(searches)
    for i in range(5):
        print(f"{len(searches_by_size[i])} searches with {i} players")

    x = [search.average_rating for search in searches]
    bins = [-600, -500, -400, -300, -200, -100, 0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100]
    fig, ax = plt.subplots()
    ax.hist(x, bins, density=True)
    ax.grid(axis='x')
    plt.show()


@pytest.mark.performance
def test_team_matchmaker_performance(player_factory, bench, caplog):
    # Disable debug logging for performance
    caplog.set_level(logging.INFO)
    num_searches = 200
    matchmaker = TeamMatchMaker()

    searches = [Search([player_factory(1500, 500, ladder_games=1)]) for _ in range(num_searches)]

    with bench:
        matchmaker.find(searches, 4, 1000)

    assert bench.elapsed() < 0.5


def test_team_matchmaker_algorithm(player_factory):
    matchmaker = TeamMatchMaker()
    s = make_searches(
        [1251, 1116, 1038, 1332, 1271, 1142, 1045, 1347, 1359, 1348, 1227, 1118, 1058, 1338, 1271, 1137, 1025],
        player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    c2 = CombinedSearch(*[s.pop(), s.pop()])
    c3 = CombinedSearch(*[s.pop(), s.pop()])
    c4 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    s.append(c1)
    s.append(c2)
    s.append(c3)
    s.append(c4)

    matches, unmatched = matchmaker.find(s, 4, 1000)

    assert set(matches[1][0].get_original_searches()) == {c1, s[2], s[5]}
    assert set(matches[1][1].get_original_searches()) == {c3, s[1], s[6]}
    assert set(matches[0][0].get_original_searches()) == {c4, s[4]}
    assert set(matches[0][1].get_original_searches()) == {c2, s[0], s[3]}
    assert set(unmatched) == {s[7]}
    for match in matches:
        assert matchmaker.assign_game_quality(match, 4, 1000).quality > config.MINIMUM_GAME_QUALITY


def test_team_matchmaker_algorithm_2(player_factory):
    matchmaker = TeamMatchMaker()
    s = make_searches(
        [227, 1531, 1628, 1722, 1415, 1146, 937, 1028, 1315, 1236, 1125, 1252, 1185, 1333, 1263, 1184, 1037],
        player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    c2 = CombinedSearch(*[s.pop(), s.pop()])
    c3 = CombinedSearch(*[s.pop(), s.pop()])
    c4 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    s.append(c1)
    s.append(c2)
    s.append(c3)
    s.append(c4)

    matches, unmatched = matchmaker.find(s, 4, 1000)

    assert set(matches[0][0].get_original_searches()) == {c4, s[4]}
    assert set(matches[0][1].get_original_searches()) == {c2, c3}
    assert set(unmatched) == {s[0], s[1], s[2], s[3], s[5], s[6], s[7], c1}
    for match in matches:
        assert matchmaker.assign_game_quality(match, 4, 1000).quality > config.MINIMUM_GAME_QUALITY


@pytest.mark.slow
@settings(suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow])
@given(st_searches_list_with_player_size(min_size=2, max_players=4, max_size=8))
def test_make_even_teams(searches_with_player_size):
    searches = searches_with_player_size[0]
    team_size = searches_with_player_size[1]
    assume(sum(len(search.players) for search in searches) == 2 * team_size)

    try:
        teams = TeamMatchMaker().make_teams(searches, team_size)
        assert len(teams[0].players) == team_size
        assert len(teams[1].players) == team_size
    except UnevenTeamsException:
        pass


def test_make_fair_teams(player_factory):
    s = make_searches([925, 1084, 1015, 1094, 1718, 1526, 1637, 1403], player_factory)
    team_a = CombinedSearch(*[s[1], s[2], s[4], s[7]])
    team_b = CombinedSearch(*[s[0], s[3], s[5], s[6]])

    teams = TeamMatchMaker().make_teams(s, 4)

    # By converting to a set we don't have to worry about order
    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)
    assert abs(teams[0].cumulative_rating - teams[1].cumulative_rating) < 50


def test_make_fair_teams_2(player_factory):
    s = make_searches([1310, 620, 1230, 1070, 1180, 1090, 800, 1060], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    c2 = CombinedSearch(*[s.pop(), s.pop()])
    s.append(c1)
    s.append(c2)
    team_a = CombinedSearch(*[c2, s[0], s[1]])
    team_b = CombinedSearch(*[c1, s[2], s[3]])

    teams = TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)
    assert abs(teams[0].cumulative_rating - teams[1].cumulative_rating) < 50


def test_make_teams_with_negative_rated_players(player_factory):
    s = make_searches([625, -184, -15, 94, 403, 526, 637, -218], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    s.append(c1)
    team_a = CombinedSearch(*[s[0], s[1], s[3], s[4]])
    team_b = CombinedSearch(*[s[2], s[5], s[6]])

    teams = TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)
    assert abs(teams[0].cumulative_rating - teams[1].cumulative_rating) < 50


def test_make_teams_with_full_sized_search(player_factory):
    s = make_searches([925, 1084, 1015, 1094, 1403, 1526, 1637, 1718], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop(), s.pop(), s.pop()])
    s.append(c1)
    team_a = CombinedSearch(*[c1])
    team_b = CombinedSearch(*[s[0], s[1], s[2], s[3]])

    teams = TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)


def test_make_teams_with_almost_full_sized_search(player_factory):
    s = make_searches([1415, 125, 1294, 584, 1303, 1526, 1237, 1218], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    s.append(c1)

    team_a = CombinedSearch(*[c1, s[3]])
    team_b = CombinedSearch(*[s[0], s[1], s[2], s[4]])
    teams = TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)


def test_ignore_impossible_team_splits(player_factory):
    s = make_searches([1415, 1250, 1294, 1584, 1303, 1526, 1237, 1218], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    c2 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    c3 = CombinedSearch(*[s.pop(), s.pop()])
    s.append(c1)
    s.append(c2)
    s.append(c3)

    matches, unmatched = TeamMatchMaker().find(s, 4, 1000)

    assert matches == []
    assert set(unmatched) == set(s)


@given(team_a=st_searches(4), team_b=st_searches(4))
def test_game_quality(team_a, team_b):
    config.MINORITY_BONUS = 0

    game = TeamMatchMaker().assign_game_quality((team_a, team_b), 4, 1000)

    assert game.quality <= 1.0


@given(player=st_players())
def test_maximum_game_quality_for_even_teams(player):
    search = Search([player])
    team_a = CombinedSearch(*[search] * 4)
    team_b = CombinedSearch(*[search] * 4)
    game = TeamMatchMaker().assign_game_quality((team_a, team_b), 4, 1000)

    assert 1.0 <= game.quality <= 1.0 + config.MINORITY_BONUS


def test_low_game_quality_for_high_rating_disparity(player_factory):
    s = make_searches([100, 100, 4000, 4000, 4000, 4000, 100, 100], player_factory)
    team_a = CombinedSearch(*[s[0], s[1], s[2], s[3]])
    team_b = CombinedSearch(*[s[4], s[5], s[6], s[7]])
    game = TeamMatchMaker().assign_game_quality((team_a, team_b), 4, 1000)

    assert game.quality < 0.0


def test_low_game_quality_for_unfair_teams(player_factory):
    s = make_searches([100, 100, 100, 100, 4000, 4000, 4000, 4000], player_factory)
    team_a = CombinedSearch(*[s[0], s[1], s[2], s[3]])
    team_b = CombinedSearch(*[s[4], s[5], s[6], s[7]])
    game = TeamMatchMaker().assign_game_quality((team_a, team_b), 4, 1000)

    assert game.quality < 0.0


@given(st_searches_list(max_players=1, min_size=6, max_size=6))
def test_game_quality_time_bonus(s):
    matchmaker = TeamMatchMaker()
    team_a = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    team_b = CombinedSearch(*[c1, s.pop()])
    quality_before = matchmaker.assign_game_quality((team_a, team_b), 3, 1000).quality

    team_a.register_failed_matching_attempt()
    team_b.register_failed_matching_attempt()
    quality_after = matchmaker.assign_game_quality((team_a, team_b), 3, 1000).quality

    if team_a.has_high_rated_player() or team_b.has_high_rated_player():
        num_newbies = 0
    else:
        num_newbies = team_a.num_newbies() + team_b.num_newbies()

    assert (
        quality_before
        # player number / team size * time bonus
        + 6 / 3 * config.TIME_BONUS
        + num_newbies / 3 * config.NEWBIE_TIME_BONUS
        == pytest.approx(quality_after)
    )


@given(st_searches_list(max_players=1, min_size=6, max_size=6))
def test_game_quality_max_time_bonus(s):
    matchmaker = TeamMatchMaker()
    team_a = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    team_b = CombinedSearch(*[c1, s.pop()])
    quality_before = matchmaker.assign_game_quality((team_a, team_b), 3, 1000).quality

    for _ in range(30):
        team_a.register_failed_matching_attempt()
        team_b.register_failed_matching_attempt()
    quality_after = matchmaker.assign_game_quality((team_a, team_b), 3, 1000).quality

    if team_a.has_high_rated_player() or team_b.has_high_rated_player():
        num_newbies = 0
    else:
        num_newbies = team_a.num_newbies() + team_b.num_newbies()

    assert (
        quality_before
        # player number / team size * time bonus
        + 6 / 3 * config.MAXIMUM_TIME_BONUS
        + num_newbies / 3 * config.MAXIMUM_NEWBIE_TIME_BONUS
        == pytest.approx(quality_after)
    )


@pytest.mark.slow
@given(st_searches_list_with_index(max_players=4, min_size=2))
def test_pick_neighboring_players(searches_with_index):
    searches = searches_with_index[0]
    index = searches_with_index[1]
    try:
        participants = TeamMatchMaker().pick_neighboring_players(searches, index, 4)
        assert sum(len(search.players) for search in participants) == 8
    except NotEnoughPlayersException:
        assume(False)


@pytest.mark.slow
@given(st_searches_list(max_players=1, min_size=8))
def test_pick_neighboring_players_from_start(searches):
    participants = TeamMatchMaker().pick_neighboring_players(searches, 0, 4)

    assert sum(len(search.players) for search in participants) == 8
    assert set(participants) == set(searches[:8])


@pytest.mark.slow
@given(st_searches_list(max_players=1, min_size=8))
def test_pick_neighboring_players_from_end(searches):
    index = len(searches) - 1

    participants = TeamMatchMaker().pick_neighboring_players(searches, index, 4)

    assert sum(len(search.players) for search in participants) == 8
    assert set(participants) == set(searches[-8:])


def test_pick_noncolliding_games_no_games():
    assert TeamMatchMaker().pick_noncolliding_games([]) == []


@given(st_game_candidates_list(min_size=1))
def test_pick_noncolliding_games(games):
    max_quality_game = max(games, key=lambda game: game.quality)

    matches = TeamMatchMaker().pick_noncolliding_games(games)

    while matches:
        match = matches.pop()
        for other_match in matches:
            assert set(search for team in match for search in team.get_original_searches()).isdisjoint(
                search for team in other_match for search in team.get_original_searches()
            )
    if matches:
        assert max_quality_game.match == matches[0]
