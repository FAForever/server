from concurrent.futures import CancelledError, TimeoutError
from unittest.mock import Mock
import asyncio
import pytest
from server.matchmaker import MatchmakerQueue, Search
from server.players import Player
import server.config as config
from tests import CoroMock


@pytest.fixture
def matchmaker_queue(player_service, game_service):
    return MatchmakerQueue('test_queue', player_service, Mock())

@pytest.fixture
def matchmaker_players():
    return Player('Dostya',   id=1, ladder_rating=(2300, 64), numGames=(config.NEWBIE_MIN_GAMES+1)), \
           Player('Brackman', id=2, ladder_rating=(1200, 72), numGames=(config.NEWBIE_MIN_GAMES+1)), \
           Player('Zoidberg', id=3, ladder_rating=(1300, 175), numGames=(config.NEWBIE_MIN_GAMES+1)), \
           Player('QAI',      id=4, ladder_rating=(2350, 125), numGames=(config.NEWBIE_MIN_GAMES+1)), \
           Player('Rhiza',    id=5, ladder_rating=(1200, 175), numGames=(config.NEWBIE_MIN_GAMES+1)), \
           Player('Newbie',   id=6, ladder_rating=(1200, 175), numGames=(config.NEWBIE_MIN_GAMES-1))

@pytest.fixture
def matchmaker_players_all_match():
    return Player('Dostya',   id=1, ladder_rating=(1500, 50), numGames=(config.NEWBIE_MIN_GAMES+1)), \
           Player('Brackman', id=2, ladder_rating=(1500, 50), numGames=(config.NEWBIE_MIN_GAMES+1)), \
           Player('Zoidberg', id=3, ladder_rating=(1500, 50), numGames=(config.NEWBIE_MIN_GAMES+1)), \
           Player('QAI',      id=4, ladder_rating=(1500, 50), numGames=(config.NEWBIE_MIN_GAMES+1)), \
           Player('Rhiza',    id=5, ladder_rating=(1500, 50), numGames=(config.NEWBIE_MIN_GAMES+1))

def test_newbie_min_games(mocker, loop, matchmaker_players):
    p1, _, _, _, _, p6 = matchmaker_players
    s1, s6 = Search(p1), Search(p6)
    assert s1.rating == p1.ladder_rating and s6.rating != p6.ladder_rating

def test_search_threshold(mocker, loop, matchmaker_players):
    s = Search(matchmaker_players[0])
    assert s.match_threshold <= 1
    assert s.match_threshold >= 0

def test_search_quality_equivalence(mocker, loop, matchmaker_players):
    p1, _, _, p4, _, _ = matchmaker_players
    s1, s4 = Search(p1), Search(p4)
    assert s1.quality_with(s4) == s4.quality_with(s1)

def test_search_quality(mocker, loop, matchmaker_players):
    p1, _, p3, _, p5, p6 = matchmaker_players
    s1, s3, s5, s6 = Search(p1), Search(p3), Search(p5), Search(p6)
    assert s3.quality_with(s5) > 0.7 and s1.quality_with(s6) < 0.2

@asyncio.coroutine
def test_search_match(mocker, loop, matchmaker_players):
    p1, _, _, p4, _, _ = matchmaker_players
    s1, s4 = Search(p1), Search(p4)
    assert s1.matches_with(s4)

@asyncio.coroutine
def test_search_no_match(mocker, loop, matchmaker_players):
    p1, p2, _, _, _, _ = matchmaker_players
    s1, s2 = Search(p1), Search(p2)
    assert not s1.matches_with(s2)

@asyncio.coroutine
def test_search_await(mocker, loop, matchmaker_players):
    p1, p2, _, _, _, _ = matchmaker_players
    s1, s2 = Search(p1), Search(p2)
    assert not s1.matches_with(s2)
    await_coro = asyncio.async(s1.await_match())
    s1.match(s2)
    yield from asyncio.wait_for(await_coro, 1)
    assert await_coro.done()

@asyncio.coroutine
def test_queue_race(mocker, player_service, matchmaker_queue):
    p1, p2, p3 = Player('Dostya', id=1, ladder_rating=(2300, 150), numGames=(config.NEWBIE_MIN_GAMES+1)), \
                 Player('Brackman', id=2, ladder_rating=(2200, 150), numGames=(config.NEWBIE_MIN_GAMES+1)), \
                 Player('Zoidberg', id=3, ladder_rating=(2300, 125), numGames=(config.NEWBIE_MIN_GAMES+1))

    player_service.players = {p1.id: p1, p2.id:p2, p3.id:p3}

    matchmaker_queue.game_service.ladder_service.start_game = CoroMock()

    try:
        yield from asyncio.gather(asyncio.wait_for(matchmaker_queue.search(p1), 0.1),
                                  asyncio.wait_for(matchmaker_queue.search(p2), 0.1),
                                  asyncio.wait_for(matchmaker_queue.search(p3), 0.1))
    except (TimeoutError, CancelledError):
        pass

    assert len(matchmaker_queue) == 0

@asyncio.coroutine
def test_queue_cancel(mocker, player_service, matchmaker_queue, matchmaker_players):
    # Turn list of players into map from ids to players.
    player_service.players = dict(map(lambda x: (x.id, x), list(matchmaker_players)))

    s1, s2 = Search(matchmaker_players[1]), Search(matchmaker_players[2])
    matchmaker_queue.push(s1)
    s1.cancel()
    try:
        yield from asyncio.wait_for(matchmaker_queue.search(s2.player, search=s2), 0.01)
    except (TimeoutError, CancelledError):
        pass

    assert not s1.is_matched
    assert not s2.is_matched

async def test_queue_mid_cancel(mocker, player_service, matchmaker_queue, matchmaker_players_all_match):
    # Turn list of players into map from ids to players.
    player_service.players = dict(map(lambda x: (x.id, x), list(matchmaker_players_all_match)))

    matchmaker_queue.game_service.ladder_service.start_game = CoroMock()

    s1, s2, s3 = Search(matchmaker_players_all_match[1]),\
                 Search(matchmaker_players_all_match[2]),\
                 Search(matchmaker_players_all_match[3])
    asyncio.ensure_future(matchmaker_queue.search(s1.player, search=s1))
    asyncio.ensure_future(matchmaker_queue.search(s2.player, search=s2))
    s1.cancel()
    try:
        await asyncio.wait_for(matchmaker_queue.search(s3.player, search=s3), 0.1)
    except CancelledError:
        pass

    assert not s1.is_matched
    assert s2.is_matched
    assert s3.is_matched
    assert len(matchmaker_queue) == 0

