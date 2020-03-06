import asyncio
import functools
import random
from collections import deque
from concurrent.futures import CancelledError, TimeoutError

import mock
import pytest
import server.config as config
from server.matchmaker import MatchmakerQueue, PopTimer, Search
from server.rating import RatingType
from tests.utils import fast_forward

pytestmark = pytest.mark.asyncio


@pytest.fixture
def p(player_factory):
    return functools.partial(player_factory, with_lobby_connection=False)


@pytest.fixture
def matchmaker_queue(game_service):
    return MatchmakerQueue('test_queue', game_service=mock.Mock())


@pytest.fixture
def matchmaker_players(p):
    return p('Dostya', player_id=1, ladder_rating=(2300, 64), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           p('Brackman', player_id=2, ladder_rating=(1200, 72), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           p('Zoidberg', player_id=3, ladder_rating=(1300, 175), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           p('QAI', player_id=4, ladder_rating=(2350, 125), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           p('Rhiza', player_id=5, ladder_rating=(1200, 175), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           p('Newbie', player_id=6, ladder_rating=(1200, 175), ladder_games=(config.NEWBIE_MIN_GAMES - 1))


@pytest.fixture
def matchmaker_players_all_match(p):
    return p('Dostya', player_id=1, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           p('Brackman', player_id=2, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           p('Zoidberg', player_id=3, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           p('QAI', player_id=4, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           p('Rhiza', player_id=5, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1))


async def test_is_ladder_newbie(matchmaker_players):
    pro, _, _, _, _, newbie = matchmaker_players
    assert Search._is_ladder_newbie(pro) is False
    assert Search._is_ladder_newbie(newbie)


async def test_is_single_newbie(matchmaker_players):
    pro, _, _, _, _, newbie = matchmaker_players

    single_newbie = Search([newbie])
    single_pro = Search([pro])
    two_newbies = Search([newbie, newbie])
    two_pros = Search([pro, pro])
    two_mixed = Search([newbie, pro])

    assert single_newbie.is_single_ladder_newbie()
    assert single_pro.is_single_ladder_newbie() is False
    assert two_newbies.is_single_ladder_newbie() is False
    assert two_pros.is_single_ladder_newbie() is False
    assert two_mixed.is_single_ladder_newbie() is False


async def test_newbies_have_adjusted_rating(matchmaker_players):
    pro, _, _, _, _, newbie = matchmaker_players
    s1, s6 = Search([pro]), Search([newbie])
    assert s1.ratings[0] == pro.ratings[RatingType.LADDER_1V1]
    assert s6.ratings[0] != newbie.ratings[RatingType.LADDER_1V1]


async def test_search_threshold(matchmaker_players):
    s = Search([matchmaker_players[0]])
    assert s.match_threshold <= 1
    assert s.match_threshold >= 0


async def test_search_threshold_of_single_old_players_is_high(p):
    old_player = p('experienced_player', player_id=1, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1))
    s = Search([old_player])
    assert s.match_threshold >= 0.6


async def test_search_threshold_of_team_old_players_is_high(p):
    old_player = p('experienced_player', player_id=1, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1))
    another_old_player = p('another experienced_player', player_id=2, ladder_rating=(1600, 60), ladder_games=(config.NEWBIE_MIN_GAMES + 1))
    s = Search([old_player, another_old_player])
    assert s.match_threshold >= 0.6


async def test_search_threshold_of_single_new_players_is_low(p):
    new_player = p('new_player', player_id=1, ladder_rating=(1500, 500), ladder_games=1)
    s = Search([new_player])
    assert s.match_threshold <= 0.4


async def test_search_threshold_of_team_new_players_is_low(p):
    new_player = p('new_player', player_id=1, ladder_rating=(1500, 500), ladder_games=1)
    another_new_player = p('another_new_player', player_id=2, ladder_rating=(1450, 450), ladder_games=1)
    s = Search([new_player, another_new_player])
    assert s.match_threshold <= 0.4


async def test_search_quality_equivalence(matchmaker_players):
    p1, _, _, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1]), Search([p4])
    assert s1.quality_with(s4) == s4.quality_with(s1)


async def test_search_quality(matchmaker_players):
    p1, _, p3, _, p5, p6 = matchmaker_players
    s1, s3, s5, s6 = Search([p1]), Search([p3]), Search([p5]), Search([p6])
    assert s3.quality_with(s5) > 0.7 and s1.quality_with(s6) < 0.2


async def test_search_match(matchmaker_players):
    p1, _, _, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1]), Search([p4])
    assert s1.matches_with(s4)


async def test_search_threshold_low_enough_to_play_yourself(matchmaker_players):
    for player in matchmaker_players:
        s = Search([player])
        assert s.matches_with(s)


async def test_search_team_match(matchmaker_players):
    p1, p2, p3, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1, p3]), Search([p2, p4])
    assert s1.matches_with(s4)


async def test_search_team_not_match(matchmaker_players):
    p1, p2, p3, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1, p4]), Search([p2, p3])
    assert not s1.matches_with(s4)


async def test_search_no_match(matchmaker_players):
    p1, p2, _, _, _, _ = matchmaker_players
    s1, s2 = Search([p1]), Search([p2])
    assert not s1.matches_with(s2)


async def test_search_no_match_wrong_type(matchmaker_players):
    p1, _, _, _, _, _ = matchmaker_players
    s1 = Search([p1])
    assert not s1.matches_with(42)


async def test_search_boundaries(matchmaker_players):
    p1 = matchmaker_players[0]
    s1 = Search([p1])
    assert p1.ratings[RatingType.LADDER_1V1][0] > s1.boundary_80[0]
    assert p1.ratings[RatingType.LADDER_1V1][0] < s1.boundary_80[1]
    assert p1.ratings[RatingType.LADDER_1V1][0] > s1.boundary_75[0]
    assert p1.ratings[RatingType.LADDER_1V1][0] < s1.boundary_75[1]


async def test_search_expansion_controlled_by_failed_matching_attempts(matchmaker_players, mocker):
    p1 = matchmaker_players[0]
    s1 = Search([p1])

    assert s1.search_expansion == 0.0

    s1.register_failed_matching_attempt()
    assert s1.search_expansion > 0.0

    # Make sure that the expansion stops at some point
    for _ in range(100):
        s1.register_failed_matching_attempt()
    e1 = s1.search_expansion

    s1.register_failed_matching_attempt()
    assert e1 == s1.search_expansion
    assert e1 == config.LADDER_SEARCH_EXPANSION_MAX


async def test_search_await(matchmaker_players):
    p1, p2, _, _, _, _ = matchmaker_players
    s1, s2 = Search([p1]), Search([p2])
    assert not s1.matches_with(s2)
    await_coro = asyncio.ensure_future(s1.await_match())
    s1.match(s2)
    await asyncio.wait_for(await_coro, 1)
    assert await_coro.done()


async def test_queue_time_until_next_pop():
    t1 = PopTimer("test_1")
    t2 = PopTimer("test_2")

    assert t1.time_until_next_pop(0, 0) == config.QUEUE_POP_TIME_MAX
    # If the desired number of players is not reached within the maximum waiting
    # time, then the next round must wait for the maximum allowed time as well.
    a1 = t1.time_until_next_pop(
        num_queued=config.QUEUE_POP_DESIRED_PLAYERS - 1,
        time_queued=config.QUEUE_POP_TIME_MAX
    )
    assert a1 == config.QUEUE_POP_TIME_MAX

    # If there are more players than expected, the time should drop
    a2 = t1.time_until_next_pop(
        num_queued=config.QUEUE_POP_DESIRED_PLAYERS * 2,
        time_queued=config.QUEUE_POP_TIME_MAX
    )
    assert a2 < a1

    # Make sure that queue moving averages are calculated independently
    assert t2.time_until_next_pop(0, 0) == config.QUEUE_POP_TIME_MAX


async def test_queue_pop_time_moving_average_size():
    t1 = PopTimer("test_1")

    for _ in range(100):
        t1.time_until_next_pop(100, 1)

    # The rate should be extremely high, meaning the pop time should be low
    assert t1.time_until_next_pop(100, 1) < 1

    for _ in range(config.QUEUE_POP_TIME_MOVING_AVG_SIZE):
        t1.time_until_next_pop(0, 100)

    # The rate should be extremely low, meaning the pop time should be high
    assert t1.time_until_next_pop(0, 100) == config.QUEUE_POP_TIME_MAX


@fast_forward(3)
async def test_queue_matches(matchmaker_queue):
    matches = [random.randrange(0, 1 << 20) for _ in range(20)]
    matchmaker_queue._matches = deque(matches)

    async def call_shutdown():
        await asyncio.sleep(1)
        matchmaker_queue.shutdown()

    asyncio.ensure_future(call_shutdown())
    collected_matches = [match async for match in matchmaker_queue.iter_matches()]

    assert collected_matches == matches


async def test_shutdown_matchmaker(matchmaker_queue):
    matchmaker_queue.shutdown()
    # Verify that no matches are yielded after shutdown is called
    async for _ in matchmaker_queue.iter_matches():
        assert False


async def test_queue_many(player_service, matchmaker_queue, p):
    p1, p2, p3 = p('Dostya', player_id=1, ladder_rating=(2200, 150), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
                 p('Brackman', player_id=2, ladder_rating=(1500, 150), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
                 p('Zoidberg', player_id=3, ladder_rating=(1500, 125), ladder_games=(config.NEWBIE_MIN_GAMES + 1))

    player_service.players = {p1.id: p1, p2.id: p2, p3.id: p3}
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


async def test_queue_race(player_service, matchmaker_queue, p):
    p1, p2, p3 = p('Dostya', player_id=1, ladder_rating=(2300, 150), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
                 p('Brackman', player_id=2, ladder_rating=(2200, 150), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
                 p('Zoidberg', player_id=3, ladder_rating=(2300, 125), ladder_games=(config.NEWBIE_MIN_GAMES + 1))

    player_service.players = {p1.id: p1, p2.id: p2, p3.id: p3}

    async def find_matches():
        await asyncio.sleep(0.01)
        await matchmaker_queue.find_matches()
    try:
        await asyncio.gather(
            asyncio.wait_for(matchmaker_queue.search(Search([p1])), 0.1),
            asyncio.wait_for(matchmaker_queue.search(Search([p2])), 0.1),
            asyncio.wait_for(matchmaker_queue.search(Search([p3])), 0.1),
            asyncio.ensure_future(find_matches())
        )
    except (TimeoutError, CancelledError):
        pass

    assert len(matchmaker_queue.queue) == 0


async def test_queue_cancel(player_service, matchmaker_queue, matchmaker_players):
    # Turn list of players into map from ids to players.
    player_service.players = dict(map(lambda x: (x.id, x), list(matchmaker_players)))

    s1, s2 = Search([matchmaker_players[1]]), Search([matchmaker_players[2]])
    matchmaker_queue.push(s1)
    s1.cancel()
    try:
        await asyncio.wait_for(matchmaker_queue.search(s2), 0.01)
    except (TimeoutError, CancelledError):
        pass

    assert not s1.is_matched
    assert not s2.is_matched


async def test_queue_mid_cancel(player_service, matchmaker_queue, matchmaker_players_all_match):
    # Turn list of players into map from ids to players.
    player_service.players = dict(map(lambda x: (x.id, x), list(matchmaker_players_all_match)))
    p0, p1, p2, p3, _ = matchmaker_players_all_match
    (s1, s2, s3) = (Search([p1]),
                    Search([p2]),
                    Search([p3]))
    asyncio.ensure_future(matchmaker_queue.search(s1))
    asyncio.ensure_future(matchmaker_queue.search(s2))
    s1.cancel()

    async def find_matches():
        await asyncio.sleep(0.01)
        await matchmaker_queue.find_matches()
    try:
        await asyncio.gather(
            asyncio.wait_for(matchmaker_queue.search(s3), 0.1),
            asyncio.ensure_future(find_matches())
        )
    except CancelledError:
        pass

    assert not s1.is_matched
    assert s2.is_matched
    assert s3.is_matched
    assert len(matchmaker_queue.queue) == 0
