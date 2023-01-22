import asyncio
import functools
from unittest import mock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from server.config import config
from server.matchmaker import CombinedSearch, MapPool, PopTimer, Search
from server.players import PlayerState
from server.rating import RatingType

from .strategies import st_rating


@pytest.fixture(scope="module")
def player_factory(player_factory):
    return functools.partial(
        player_factory,
        ladder_games=(config.NEWBIE_MIN_GAMES + 1),
        state=PlayerState.SEARCHING_LADDER
    )


@pytest.fixture
def matchmaker_players(player_factory):
    return player_factory("Dostya", player_id=1, ladder_rating=(2300, 64)), \
        player_factory("Brackman", player_id=2, ladder_rating=(1200, 72)), \
        player_factory("Zoidberg", player_id=3, ladder_rating=(1300, 175)), \
        player_factory("QAI", player_id=4, ladder_rating=(2350, 125)), \
        player_factory("Rhiza", player_id=5, ladder_rating=(1200, 175)), \
        player_factory("Newbie", player_id=6, ladder_rating=(1200, 175), ladder_games=config.NEWBIE_MIN_GAMES - 1)


@pytest.fixture
def matchmaker_players_all_match(player_factory):
    return player_factory("Dostya", player_id=1, ladder_rating=(1500, 50)), \
        player_factory("Brackman", player_id=2, ladder_rating=(1500, 50)), \
        player_factory("Zoidberg", player_id=3, ladder_rating=(1500, 50)), \
        player_factory("QAI", player_id=4, ladder_rating=(1500, 50)), \
        player_factory("Rhiza", player_id=5, ladder_rating=(1500, 50))


def test_get_game_options_empty(queue_factory, event_loop):
    queue1 = queue_factory(params={})
    queue2 = queue_factory(params={"GameOptions": {}})

    assert queue1.get_game_options() is None
    assert queue2.get_game_options() is None


def test_get_game_options(queue_factory):
    queue = queue_factory(params={"GameOptions": {"Share": "ShareUntilDeath"}})

    assert queue.get_game_options() == {"Share": "ShareUntilDeath"}


def test_newbie_detection(matchmaker_players):
    pro, joe, _, _, _, newbie = matchmaker_players
    pro_search = Search([pro], mock.Mock())
    newbie_search = Search([newbie], mock.Mock())
    newb_team_search = Search([joe, newbie], mock.Mock())
    pro_team_search = Search([pro, joe], mock.Mock())

    assert pro_search.has_newbie() is False
    assert pro_search.is_newbie(pro) is False
    assert newbie_search.has_newbie() is True
    assert newbie_search.is_newbie(newbie) is True
    assert newb_team_search.has_newbie() is True
    assert pro_team_search.has_newbie() is False


def test_newbies_have_adjusted_rating(matchmaker_players):
    pro, _, _, _, _, newbie = matchmaker_players
    s1, s6 = Search([pro], mock.Mock()), Search([newbie], mock.Mock())
    assert s1.ratings[0] == pro.ratings[RatingType.LADDER_1V1]
    assert s6.ratings[0] < newbie.ratings[RatingType.LADDER_1V1]


@given(rating=st_rating())
def test_search_threshold(player_factory, rating):
    player = player_factory("Player", ladder_rating=rating)
    s = Search([player], mock.Mock())
    assert s.match_threshold <= 1
    assert s.match_threshold >= 0


def test_search_threshold_of_single_old_players_is_high(player_factory):
    old_player = player_factory("experienced_player", ladder_rating=(1500, 50))
    s = Search([old_player], mock.Mock())
    assert s.match_threshold >= 0.6


def test_search_threshold_of_team_old_players_is_high(player_factory):
    old_player = player_factory("experienced_player", ladder_rating=(1500, 50))
    another_old_player = player_factory("another experienced_player", ladder_rating=(1600, 60))
    s = Search([old_player, another_old_player], mock.Mock())
    assert s.match_threshold >= 0.6


def test_search_threshold_of_single_new_players_is_low(player_factory):
    new_player = player_factory("new_player", ladder_rating=(1500, 500), ladder_games=1)
    s = Search([new_player], mock.Mock())
    assert s.match_threshold <= 0.4


def test_search_threshold_of_team_new_players_is_low(player_factory):
    new_player = player_factory("new_player", ladder_rating=(1500, 500), ladder_games=1)
    another_new_player = player_factory("another_new_player", ladder_rating=(1450, 450), ladder_games=1)
    s = Search([new_player, another_new_player], mock.Mock())
    assert s.match_threshold <= 0.4


@given(rating1=st_rating(), rating2=st_rating())
def test_search_quality_equivalence(player_factory, rating1, rating2):
    p1 = player_factory("Player1", ladder_rating=rating1)
    p2 = player_factory("Player2", ladder_rating=rating2)
    s1 = Search([p1], mock.Mock())
    s2 = Search([p2], mock.Mock())
    assert s1.quality_with(s2) == s2.quality_with(s1)


def test_search_quality(matchmaker_players):
    p1, _, p3, _, p5, p6 = matchmaker_players
    s1, s3, s5, s6 = Search([p1], mock.Mock()), Search([p3], mock.Mock()), Search([p5], mock.Mock()), Search([p6],
                                                                                                             mock.Mock())
    assert s3.quality_with(s5) > 0.7 and s1.quality_with(s6) < 0.2


def test_search_match(matchmaker_players):
    p1, _, _, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1], mock.Mock()), Search([p4], mock.Mock())
    assert s1.matches_with(s4)


def test_search_threshold_low_enough_to_play_yourself(matchmaker_players):
    for player in matchmaker_players:
        s = Search([player], mock.Mock())
        assert s.matches_with(s)


def test_search_team_match(matchmaker_players):
    p1, p2, p3, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1, p3], mock.Mock()), Search([p2, p4], mock.Mock())
    assert s1.matches_with(s4)


def test_search_team_not_match(matchmaker_players):
    p1, p2, p3, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1, p4], mock.Mock()), Search([p2, p3], mock.Mock())
    assert not s1.matches_with(s4)


def test_search_no_match(matchmaker_players):
    p1, p2, _, _, _, _ = matchmaker_players
    s1, s2 = Search([p1], mock.Mock()), Search([p2], mock.Mock())
    assert not s1.matches_with(s2)


def test_search_no_match_wrong_type(matchmaker_players):
    p1, _, _, _, _, _ = matchmaker_players
    s1 = Search([p1], mock.Mock())
    assert not s1.matches_with(42)


def test_search_boundaries(matchmaker_players):
    p1 = matchmaker_players[0]
    s1 = Search([p1], mock.Mock())
    assert p1.ratings[RatingType.LADDER_1V1][0] > s1.boundary_80[0]
    assert p1.ratings[RatingType.LADDER_1V1][0] < s1.boundary_80[1]
    assert p1.ratings[RatingType.LADDER_1V1][0] > s1.boundary_75[0]
    assert p1.ratings[RatingType.LADDER_1V1][0] < s1.boundary_75[1]


def test_search_expansion_controlled_by_failed_matching_attempts(matchmaker_players):
    p1 = matchmaker_players[1]
    s1 = Search([p1], mock.Mock())

    assert s1.search_expansion == 0.0

    s1.register_failed_matching_attempt()
    assert s1.search_expansion == config.LADDER_SEARCH_EXPANSION_STEP

    # Make sure that the expansion stops at some point
    for _ in range(100):
        s1.register_failed_matching_attempt()
    e1 = s1.search_expansion

    s1.register_failed_matching_attempt()
    assert e1 == s1.search_expansion
    assert e1 == config.LADDER_SEARCH_EXPANSION_MAX


def test_search_expansion_for_top_players(matchmaker_players):
    p1 = matchmaker_players[0]
    s1 = Search([p1], mock.Mock())

    assert s1.search_expansion == 0.0

    s1.register_failed_matching_attempt()
    assert s1.search_expansion == config.LADDER_TOP_PLAYER_SEARCH_EXPANSION_STEP

    # Make sure that the expansion stops at some point
    for _ in range(100):
        s1.register_failed_matching_attempt()
    e1 = s1.search_expansion

    s1.register_failed_matching_attempt()
    assert e1 == s1.search_expansion
    assert e1 == config.LADDER_TOP_PLAYER_SEARCH_EXPANSION_MAX


async def test_search_await(matchmaker_players):
    p1, p2, _, _, _, _ = matchmaker_players
    s1, s2 = Search([p1], mock.Mock()), Search([p2], mock.Mock())
    assert not s1.matches_with(s2)
    await_coro = asyncio.create_task(s1.await_match())
    s1.match(s2)
    await asyncio.wait_for(await_coro, 1)
    assert await_coro.done()


def test_combined_search_attributes(matchmaker_players):
    p1, p2, p3, _, _, _ = matchmaker_players
    s1 = Search([p1, p2], mock.Mock())
    s2 = Search([p3], mock.Mock())
    s2.register_failed_matching_attempt()
    search = CombinedSearch(s1, s2)
    assert search.players == [p1, p2, p3]
    assert search.raw_ratings == [
        p1.ratings[RatingType.LADDER_1V1],
        p2.ratings[RatingType.LADDER_1V1],
        p3.ratings[RatingType.LADDER_1V1]
    ]
    assert search.failed_matching_attempts == 1

    search.register_failed_matching_attempt()
    assert search.failed_matching_attempts == 2


def test_queue_time_until_next_pop(queue_factory):
    team_size = 2
    t1 = PopTimer()
    t1.queues = [queue_factory(team_size=team_size)]
    t2 = PopTimer()
    t2.queues = [queue_factory(team_size=team_size)]

    desired_players = config.QUEUE_POP_DESIRED_MATCHES * team_size * 2

    assert t1.time_until_next_pop(0, 0) == config.QUEUE_POP_TIME_MAX
    # If the desired number of players is not reached within the maximum waiting
    # time, then the next round must wait for the maximum allowed time as well.
    a1 = t1.time_until_next_pop(
        num_queued=desired_players - 1,
        time_queued=config.QUEUE_POP_TIME_MAX
    )
    assert a1 == config.QUEUE_POP_TIME_MAX

    # If there are more players than expected, the time should drop
    a2 = t1.time_until_next_pop(
        num_queued=desired_players * 2,
        time_queued=config.QUEUE_POP_TIME_MAX
    )
    assert a2 < a1

    # Make sure that queue moving averages are calculated independently
    assert t2.time_until_next_pop(0, 0) == config.QUEUE_POP_TIME_MAX


def test_queue_pop_time_moving_average_size(queue_factory):
    t1 = PopTimer()
    t1.queues = [queue_factory()]

    for _ in range(100):
        t1.time_until_next_pop(100, 1)

    # The rate should be extremely high, meaning the pop time should be low
    assert t1.time_until_next_pop(100, 1) < 1

    for _ in range(config.QUEUE_POP_TIME_MOVING_AVG_SIZE):
        t1.time_until_next_pop(0, 100)

    # The rate should be extremely low, meaning the pop time should be high
    assert t1.time_until_next_pop(0, 100) == config.QUEUE_POP_TIME_MAX


@given(rating=st.integers())
def test_queue_map_pools_empty(queue_factory, rating):
    queue = queue_factory()
    assert queue.get_map_pool_for_rating(rating) is None


@given(rating=st.integers())
def test_queue_map_pools_any_range(queue_factory, rating):
    queue = queue_factory()
    map_pool = MapPool(0, "pool")
    queue.add_map_pool(map_pool, None, None)

    assert queue.get_map_pool_for_rating(rating) is map_pool


@given(rating=st.integers(), low=st.integers())
def test_queue_map_pools_lower_bound(queue_factory, rating, low):
    queue = queue_factory()
    map_pool = MapPool(0, "pool")
    queue.add_map_pool(map_pool, low, None)

    if rating < low:
        assert queue.get_map_pool_for_rating(rating) is None
    else:
        assert queue.get_map_pool_for_rating(rating) is map_pool


@given(rating=st.integers(), high=st.integers())
def test_queue_map_pools_upper_bound(queue_factory, rating, high):
    queue = queue_factory()
    map_pool = MapPool(0, "pool")
    queue.add_map_pool(map_pool, None, high)

    if rating > high:
        assert queue.get_map_pool_for_rating(rating) is None
    else:
        assert queue.get_map_pool_for_rating(rating) is map_pool


@given(rating=st.integers(), low=st.integers(), high=st.integers())
def test_queue_map_pools_bound(queue_factory, rating, low, high):
    queue = queue_factory()
    map_pool = MapPool(0, "pool")
    queue.add_map_pool(map_pool, low, high)

    if low <= rating <= high:
        assert queue.get_map_pool_for_rating(rating) is map_pool
    else:
        assert queue.get_map_pool_for_rating(rating) is None


@given(
    rating=st.integers(),
    low1=st.integers(),
    high1=st.integers(),
    low2=st.integers(),
    high2=st.integers()
)
def test_queue_multiple_map_pools(
    queue_factory, rating, low1, high1, low2, high2
):
    queue = queue_factory()
    map_pool1 = MapPool(0, "pool1")
    map_pool2 = MapPool(1, "pool2")
    queue.add_map_pool(map_pool1, low1, high1)
    queue.add_map_pool(map_pool2, low2, high2)

    if low1 <= rating <= high1:
        assert queue.get_map_pool_for_rating(rating) is map_pool1
    elif low2 <= rating <= high2:
        assert queue.get_map_pool_for_rating(rating) is map_pool2
    else:
        assert queue.get_map_pool_for_rating(rating) is None


async def test_queue_race(matchmaker_queue, player_factory):
    p1, p2, p3 = player_factory("Dostya", ladder_rating=(2300, 150)), \
        player_factory("Brackman", ladder_rating=(2200, 150)), \
        player_factory("Zoidberg", ladder_rating=(2300, 125))

    async def find_matches():
        await asyncio.sleep(0.01)
        await matchmaker_queue.find_matches()

    try:
        await asyncio.gather(
            asyncio.wait_for(matchmaker_queue.search(Search([p1], mock.Mock())), 0.1),
            asyncio.wait_for(matchmaker_queue.search(Search([p2], mock.Mock())), 0.1),
            asyncio.wait_for(matchmaker_queue.search(Search([p3], mock.Mock())), 0.1),
            asyncio.create_task(find_matches())
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass

    assert len(matchmaker_queue._queue) == 0


async def test_queue_cancel(matchmaker_queue, matchmaker_players):
    s1, s2 = Search([matchmaker_players[1]], mock.Mock()), Search([matchmaker_players[2]], mock.Mock())
    matchmaker_queue.push(s1)
    s1.cancel()
    try:
        await asyncio.wait_for(matchmaker_queue.search(s2), 0.01)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass

    assert not s1.is_matched
    assert not s2.is_matched
    matchmaker_queue.on_match_found.assert_not_called()


