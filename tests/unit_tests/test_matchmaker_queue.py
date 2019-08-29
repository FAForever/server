import asyncio
import random
from collections import deque
from concurrent.futures import CancelledError, TimeoutError

import mock
import pytest
import server.config as config
from server.matchmaker import MatchmakerQueue, Search
from server.players import Player


@pytest.fixture
def matchmaker_queue(game_service):
    return MatchmakerQueue('test_queue', game_service=mock.Mock())


@pytest.fixture
def matchmaker_players():
    return Player('Dostya', player_id=1, ladder_rating=(2300, 64), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           Player('Brackman', player_id=2, ladder_rating=(1200, 72), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           Player('Zoidberg', player_id=3, ladder_rating=(1300, 175), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           Player('QAI', player_id=4, ladder_rating=(2350, 125), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           Player('Rhiza', player_id=5, ladder_rating=(1200, 175), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           Player('Newbie', player_id=6, ladder_rating=(1200, 175), ladder_games=(config.NEWBIE_MIN_GAMES - 1))


@pytest.fixture
def matchmaker_players_all_match():
    return Player('Dostya', player_id=1, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           Player('Brackman', player_id=2, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           Player('Zoidberg', player_id=3, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           Player('QAI', player_id=4, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
           Player('Rhiza', player_id=5, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1))


def test_newbie_min_games(mocker, loop, matchmaker_players):
    p1, _, _, _, _, p6 = matchmaker_players
    s1, s6 = Search([p1]), Search([p6])
    assert s1.ratings[0] == p1.ladder_rating and s6.ratings[0] != p6.ladder_rating


def test_search_threshold(mocker, loop, matchmaker_players):
    s = Search([matchmaker_players[0]])
    assert s.match_threshold <= 1
    assert s.match_threshold >= 0


def test_search_threshold_of_old_players_is_high(mocker, loop):
    old_player = Player('experienced_player', player_id=1, ladder_rating=(1500, 50), ladder_games=(config.NEWBIE_MIN_GAMES + 1))
    s = Search([old_player])
    assert s.match_threshold >= 0.6


def test_search_threshold_of_new_players_is_low(mocker, loop):
    new_player = Player('new_player', player_id=1, ladder_rating=(1500, 500), ladder_games=1)
    s = Search([new_player])
    assert s.match_threshold <= 0.4


def test_search_quality_equivalence(mocker, loop, matchmaker_players):
    p1, _, _, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1]), Search([p4])
    assert s1.quality_with(s4) == s4.quality_with(s1)


def test_search_quality(mocker, loop, matchmaker_players):
    p1, _, p3, _, p5, p6 = matchmaker_players
    s1, s3, s5, s6 = Search([p1]), Search([p3]), Search([p5]), Search([p6])
    assert s3.quality_with(s5) > 0.7 and s1.quality_with(s6) < 0.2


async def test_search_match(mocker, loop, matchmaker_players):
    p1, _, _, p4, _, _ = matchmaker_players
    s1, s4 = Search([p1]), Search([p4])
    assert s1.matches_with(s4)


def test_search_threshold_low_enough_to_play_yourself(mocker, loop, matchmaker_players):
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


async def test_search_no_match(mocker, loop, matchmaker_players):
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
    assert p1.ladder_rating[0] > s1.boundary_80[0]
    assert p1.ladder_rating[0] < s1.boundary_80[1]
    assert p1.ladder_rating[0] > s1.boundary_75[0]
    assert p1.ladder_rating[0] < s1.boundary_75[1]


def test_search_expansion(matchmaker_players, mocker):
    p1 = matchmaker_players[0]
    mocker.patch('time.time', return_value=0)
    s1 = Search([p1])

    assert s1.search_expansion == 0.0
    mocker.patch('time.time', return_value=500)
    assert s1.search_expansion > 0.0

    # Make sure that the expansion stops at some point
    mocker.patch('time.time', return_value=500_000)
    e1 = s1.search_expansion
    mocker.patch('time.time', return_value=500_300)
    assert e1 == s1.search_expansion


async def test_search_await(mocker, loop, matchmaker_players):
    p1, p2, _, _, _, _ = matchmaker_players
    s1, s2 = Search([p1]), Search([p2])
    assert not s1.matches_with(s2)
    await_coro = asyncio.ensure_future(s1.await_match())
    s1.match(s2)
    await asyncio.wait_for(await_coro, 1)
    assert await_coro.done()


def test_queue_time_until_next_pop(matchmaker_queue):
    q1 = matchmaker_queue
    q2 = MatchmakerQueue('test_queue_2', game_service=mock.Mock())

    assert q1.time_until_next_pop() == config.QUEUE_POP_TIME_MAX
    q1.queue = [None] * 5
    a1 = q1.time_until_next_pop()
    assert a1 < config.QUEUE_POP_TIME_MAX
    a2 = q1.time_until_next_pop()
    # Should be strictly less because of the moving average
    assert a2 < a1

    # Make sure that queue moving averages are claculated independently
    assert q2.time_until_next_pop() == config.QUEUE_POP_TIME_MAX


async def test_queue_matches(matchmaker_queue):
    matches = [random.randrange(0, 1 << 20) for _ in range(20)]
    matchmaker_queue._matches = deque(matches)

    async def call_shutdown():
        asyncio.sleep(1)
        matchmaker_queue.shutdown()

    asyncio.ensure_future(call_shutdown())
    collected_matches = [match async for match in matchmaker_queue.iter_matches()]

    assert collected_matches == matches


async def test_shutdown_matchmaker(matchmaker_queue):
    matchmaker_queue.shutdown()
    # Verify that no matches are yielded after shutdown is called
    async for _ in matchmaker_queue.iter_matches():
        assert False


async def test_queue_many(mocker, player_service, matchmaker_queue):
    p1, p2, p3 = Player('Dostya', player_id=1, ladder_rating=(2200, 150), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
                 Player('Brackman', player_id=2, ladder_rating=(1500, 150), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
                 Player('Zoidberg', player_id=3, ladder_rating=(1500, 125), ladder_games=(config.NEWBIE_MIN_GAMES + 1))

    player_service.players = {p1.id: p1, p2.id: p2, p3.id: p3}
    s1 = Search([p1])
    s2 = Search([p2])
    s3 = Search([p3])
    matchmaker_queue.push(s1)
    matchmaker_queue.push(s2)
    matchmaker_queue.push(s3)

    matchmaker_queue.find_matches()

    assert not s1.is_matched
    assert s2.is_matched
    assert s3.is_matched


async def test_queue_race(mocker, player_service, matchmaker_queue):
    p1, p2, p3 = Player('Dostya', player_id=1, ladder_rating=(2300, 150), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
                 Player('Brackman', player_id=2, ladder_rating=(2200, 150), ladder_games=(config.NEWBIE_MIN_GAMES + 1)), \
                 Player('Zoidberg', player_id=3, ladder_rating=(2300, 125), ladder_games=(config.NEWBIE_MIN_GAMES + 1))

    player_service.players = {p1.id: p1, p2.id: p2, p3.id: p3}

    async def find_matches():
        await asyncio.sleep(0.01)
        matchmaker_queue.find_matches()
    try:
        await asyncio.gather(
            asyncio.wait_for(matchmaker_queue.search(Search([p1])), 0.1),
            asyncio.wait_for(matchmaker_queue.search(Search([p2])), 0.1),
            asyncio.wait_for(matchmaker_queue.search(Search([p3])), 0.1),
            asyncio.ensure_future(find_matches())
        )
    except (TimeoutError, CancelledError):
        pass

    assert len(matchmaker_queue) == 0


async def test_queue_cancel(mocker, player_service, matchmaker_queue, matchmaker_players):
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


async def test_queue_mid_cancel(mocker, player_service, matchmaker_queue, matchmaker_players_all_match):
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
        matchmaker_queue.find_matches()
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
    assert len(matchmaker_queue) == 0
