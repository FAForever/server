import asyncio
import functools
import time
from unittest import mock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from server.config import config
from server.matchmaker import CombinedSearch, MapPool, Search
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


def test_get_game_options_empty(queue_factory):
    queue1 = queue_factory(params={})
    queue2 = queue_factory(params={"GameOptions": {}})

    assert queue1.get_game_options() is None
    assert queue2.get_game_options() is None


def test_get_game_options(queue_factory):
    queue = queue_factory(params={"GameOptions": {"Share": "ShareUntilDeath"}})

    assert queue.get_game_options() == {"Share": "ShareUntilDeath"}


def test_newbie_detection(matchmaker_players):
    pro, joe, _, _, _, newbie = matchmaker_players
    pro_search = Search([pro])
    newbie_search = Search([newbie])
    newb_team_search = Search([joe, newbie])
    pro_team_search = Search([pro, joe])

    assert pro_search.has_newbie() is False
    assert pro_search.is_newbie(pro) is False
    assert newbie_search.has_newbie() is True
    assert newbie_search.is_newbie(newbie) is True
    assert newb_team_search.has_newbie() is True
    assert pro_team_search.has_newbie() is False


def test_newbies_have_adjusted_rating(matchmaker_players):
    pro, _, _, _, _, newbie = matchmaker_players
    s1, s6 = Search([pro]), Search([newbie])
    assert s1.ratings[0] == pro.ratings[RatingType.LADDER_1V1]
    assert s6.ratings[0] < newbie.ratings[RatingType.LADDER_1V1]


@given(rating=st_rating())
def test_search_threshold(player_factory, rating):
    player = player_factory("Player", ladder_rating=rating)
    s = Search([player])
    assert s.match_threshold <= 1
    assert s.match_threshold >= 0


def test_search_threshold_of_single_old_players_is_high(player_factory):
    old_player = player_factory("experienced_player", ladder_rating=(1500, 50))
    s = Search([old_player])
    assert s.match_threshold >= 0.7


def test_search_threshold_of_team_old_players_is_high(player_factory):
    old_player = player_factory("experienced_player", ladder_rating=(1500, 50))
    another_old_player = player_factory("another experienced_player", ladder_rating=(1600, 60))
    s = Search([old_player, another_old_player])
    assert s.match_threshold >= 0.7


def test_search_threshold_of_single_new_players_is_low(player_factory):
    new_player = player_factory("new_player", ladder_rating=(1500, 500), ladder_games=1)
    s = Search([new_player])
    assert s.match_threshold <= 0.4
    assert s.match_threshold > 0.3


def test_search_threshold_of_team_new_players_is_low(player_factory):
    new_player = player_factory("new_player", ladder_rating=(1500, 500), ladder_games=1)
    another_new_player = player_factory("another_new_player", ladder_rating=(1450, 450), ladder_games=1)
    s = Search([new_player, another_new_player])
    assert s.match_threshold <= 0.4
    assert s.match_threshold > 0.3


def test_search_threshold_of_single_not_so_new_players_is_higher(player_factory):
    # This is roughly the deviation minimum after 10 games
    new_player = player_factory("new_player", ladder_rating=(1500, 150), ladder_games=10)
    s = Search([new_player])
    assert s.match_threshold <= 0.7
    assert s.match_threshold > 0.6


def test_search_threshold_of_single_new_players_reaches_zero(player_factory):
    new_player = player_factory("new_player", ladder_rating=(1500, 250), ladder_games=1)
    s = Search([new_player])
    for _ in range(100):
        s.register_failed_matching_attempt()
    assert s.match_threshold == 0


@given(rating1=st_rating(), rating2=st_rating())
def test_search_quality_equivalence(player_factory, rating1, rating2):
    p1 = player_factory("Player1", ladder_rating=rating1)
    p2 = player_factory("Player2", ladder_rating=rating2)
    s1 = Search([p1])
    s2 = Search([p2])
    assert s1.quality_with(s2) == s2.quality_with(s1)


def test_search_quality(matchmaker_players):
    p1, _, p3, _, p5, p6 = matchmaker_players
    s1, s3, s5, s6 = Search([p1]), Search([p3]), Search([p5]), Search([p6])
    assert s3.quality_with(s5) > 0.7 and s1.quality_with(s6) < 0.2


def test_search_match(matchmaker_players):
    p1, _, _, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1]), Search([p4])
    assert s1.matches_with(s4)


def test_search_threshold_low_enough_to_play_yourself(matchmaker_players):
    for player in matchmaker_players:
        s = Search([player])
        assert s.matches_with(s)


def test_search_team_match(matchmaker_players):
    p1, p2, p3, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1, p3]), Search([p2, p4])
    assert s1.matches_with(s4)


def test_search_team_not_match(matchmaker_players):
    p1, p2, p3, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1, p4]), Search([p2, p3])
    assert not s1.matches_with(s4)


def test_search_no_match(matchmaker_players):
    p1, p2, _, _, _, _ = matchmaker_players
    s1, s2 = Search([p1]), Search([p2])
    assert not s1.matches_with(s2)


def test_search_no_match_wrong_type(matchmaker_players):
    p1, _, _, _, _, _ = matchmaker_players
    s1 = Search([p1])
    assert not s1.matches_with(42)


def test_search_boundaries(matchmaker_players):
    p1 = matchmaker_players[0]
    s1 = Search([p1])
    assert p1.ratings[RatingType.LADDER_1V1][0] > s1.boundary_80[0]
    assert p1.ratings[RatingType.LADDER_1V1][0] < s1.boundary_80[1]
    assert p1.ratings[RatingType.LADDER_1V1][0] > s1.boundary_75[0]
    assert p1.ratings[RatingType.LADDER_1V1][0] < s1.boundary_75[1]


def test_search_expansion_controlled_by_failed_matching_attempts(matchmaker_players):
    p1 = matchmaker_players[1]
    s1 = Search([p1])

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
    s1 = Search([p1])

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


def test_search_expansion_for_newbies(matchmaker_players):
    p1 = matchmaker_players[5]
    s1 = Search([p1])

    assert s1.search_expansion == 0.0

    s1.register_failed_matching_attempt()
    assert s1.search_expansion == config.LADDER_NEWBIE_SEARCH_EXPANSION_STEP

    # Make sure that the expansion stops at some point
    for _ in range(100):
        s1.register_failed_matching_attempt()
    e1 = s1.search_expansion

    s1.register_failed_matching_attempt()
    assert e1 == s1.search_expansion
    assert e1 == config.LADDER_NEWBIE_SEARCH_EXPANSION_MAX


async def test_search_await(matchmaker_players):
    p1, p2, _, _, _, _ = matchmaker_players
    s1, s2 = Search([p1]), Search([p2])
    assert not s1.matches_with(s2)
    await_coro = asyncio.create_task(s1.await_match())
    s1.match(s2)
    await asyncio.wait_for(await_coro, 1)
    assert await_coro.done()


def test_combined_search_attributes(matchmaker_players):
    p1, p2, p3, _, _, _ = matchmaker_players
    s1 = Search([p1, p2])
    s2 = Search([p3])
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


async def test_queue_many(matchmaker_queue, player_factory):
    p1, p2, p3 = player_factory("Dostya", ladder_rating=(2200, 150)), \
        player_factory("Brackman", ladder_rating=(1500, 150)), \
        player_factory("Zoidberg", ladder_rating=(1500, 125))

    s1 = Search([p1])
    s2 = Search([p2])
    s3 = Search([p3])
    matchmaker_queue.push(s1)
    matchmaker_queue.push(s2)
    matchmaker_queue.push(s3)

    await matchmaker_queue.find_matches()

    assert not s1.is_matched
    assert s2.is_matched
    assert s3.is_matched
    matchmaker_queue.on_match_found.assert_called_once_with(
        s2, s3, matchmaker_queue
    )


async def test_queue_race(matchmaker_queue, player_factory):
    p1, p2, p3 = player_factory("Dostya", ladder_rating=(2300, 150)), \
        player_factory("Brackman", ladder_rating=(2200, 150)), \
        player_factory("Zoidberg", ladder_rating=(2300, 125))

    async def find_matches():
        await asyncio.sleep(0.01)
        await matchmaker_queue.find_matches()

    try:
        await asyncio.gather(
            asyncio.wait_for(matchmaker_queue.search(Search([p1])), 0.1),
            asyncio.wait_for(matchmaker_queue.search(Search([p2])), 0.1),
            asyncio.wait_for(matchmaker_queue.search(Search([p3])), 0.1),
            asyncio.create_task(find_matches())
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass

    assert len(matchmaker_queue._queue) == 0


async def test_queue_cancel(matchmaker_queue, matchmaker_players):
    s1, s2 = Search([matchmaker_players[1]]), Search([matchmaker_players[2]])
    matchmaker_queue.push(s1)
    s1.cancel()
    try:
        await asyncio.wait_for(matchmaker_queue.search(s2), 0.01)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass

    assert not s1.is_matched
    assert not s2.is_matched
    matchmaker_queue.on_match_found.assert_not_called()


async def test_queue_mid_cancel(matchmaker_queue, matchmaker_players_all_match):
    _, p1, p2, p3, _ = matchmaker_players_all_match
    (s1, s2, s3) = (Search([p1]),
                    Search([p2]),
                    Search([p3]))
    asyncio.create_task(matchmaker_queue.search(s1))
    asyncio.create_task(matchmaker_queue.search(s2))
    s1.cancel()

    async def find_matches():
        await asyncio.sleep(0.01)
        await matchmaker_queue.find_matches()

    try:
        await asyncio.gather(
            asyncio.wait_for(matchmaker_queue.search(s3), 0.1),
            asyncio.create_task(find_matches())
        )
    except asyncio.CancelledError:
        pass

    assert not s1.is_matched
    assert s2.is_matched
    assert s3.is_matched
    assert len(matchmaker_queue._queue) == 0
    matchmaker_queue.on_match_found.assert_called_once_with(
        s2, s3, matchmaker_queue
    )


async def test_queue_cancel_while_being_matched_registers_failed_attempt(
    matchmaker_queue, matchmaker_players_all_match
):
    p1, p2, p3, p4, _ = matchmaker_players_all_match
    searches = [Search([p1]), Search([p2]), Search([p3]), Search([p4])]
    for search in searches:
        asyncio.create_task(matchmaker_queue.search(search))

    searches[0].cancel()

    await asyncio.sleep(0.01)
    await matchmaker_queue.find_matches()

    for search in searches[1:]:
        assert search.is_matched ^ (search.failed_matching_attempts == 1)

    assert sum(search.failed_matching_attempts for search in searches[1:]) == 1
    matchmaker_queue.on_match_found.assert_called_once()


async def test_find_matches_synchronized(queue_factory):
    is_matching = False

    def find(*args):
        nonlocal is_matching

        assert not is_matching, "Function call not synchronized"
        is_matching = True

        time.sleep(0.2)

        is_matching = False
        return [], []

    queues = [queue_factory(f"Queue{i}") for i in range(5)]
    # Ensure that find_matches does not short circuit
    for queue in queues:
        queue._queue = {
            mock.Mock(players=[1]): 1,
            mock.Mock(players=[2]): 2
        }
        queue.find_teams = mock.Mock()
        queue._register_unmatched_searches = mock.Mock()
        queue.matchmaker.find = mock.Mock(side_effect=find)

    await asyncio.gather(*[
        queue.find_matches() for queue in queues
    ])


async def test_queue_pop_communicates_failed_attempts(matchmaker_queue, player_factory):
    s1 = Search([player_factory("Player1", player_id=1, ladder_rating=(3000, 50))])
    s2 = Search([player_factory("Player2", player_id=2, ladder_rating=(1000, 50))])

    matchmaker_queue.push(s1)
    assert s1.failed_matching_attempts == 0

    await matchmaker_queue.find_matches()

    assert s1.failed_matching_attempts == 1

    matchmaker_queue.push(s2)
    assert s1.failed_matching_attempts == 1
    assert s2.failed_matching_attempts == 0

    await matchmaker_queue.find_matches()

    # These searches should not have been matched
    assert s1.failed_matching_attempts == 2
    assert s2.failed_matching_attempts == 1
