from unittest import mock

import aiohttp
import pytest

from server.config import config
from server.games import GameState, GameType, VisibilityState
from server.public import (
    LIVE_GAME_FIELDS,
    PUBLIC_GAME_FIELDS,
    PUBLIC_QUEUE_FIELDS,
    PublicServer,
    is_live_game,
    is_public_lobby,
    live_game_dict,
    public_game_dict,
    public_queue_dict
)


def make_game(
    uid=1,
    state=GameState.LOBBY,
    visibility=VisibilityState.PUBLIC,
    game_type=GameType.CUSTOM,
    host="Paula_Bean",
    launched_at=None,
):
    game = mock.Mock()
    game.state = state
    game.visibility = visibility
    game.game_type = game_type
    game.host = mock.Mock(login=host) if host else None
    game.to_dict.return_value = {
        "command": "game_info",
        "visibility": visibility.value,
        "password_protected": False,
        "uid": uid,
        "title": "Some game name",
        "state": {GameState.LOBBY: "open", GameState.LIVE: "playing"}.get(state, "closed"),
        "game_type": game_type.value,
        "featured_mod": "faf",
        "sim_mods": {},
        "mapname": "scmp_007",
        "map_file_path": "maps/scmp_007.zip",
        "host": host or "",
        "num_players": 1,
        "max_players": 8,
        "hosted_at": "2026-11-10T22:00:00+00:00",
        "launched_at": launched_at,
        "rating_type": "global",
        "rating_min": None,
        "rating_max": None,
        "enforce_rating_range": False,
        "teams_ids": [{"team_id": 1, "player_ids": [1]}],
        "teams": {1: [host]},
    }
    return game


@pytest.mark.parametrize("game_type", [GameType.CUSTOM, GameType.COOP])
def test_open_public_lobby_is_listed(game_type):
    assert is_public_lobby(make_game(game_type=game_type))


@pytest.mark.parametrize("game", [
    make_game(visibility=VisibilityState.FRIENDS),
    make_game(state=GameState.INITIALIZING),
    make_game(state=GameState.LIVE),
    make_game(state=GameState.ENDED),
    make_game(game_type=GameType.MATCHMAKER),
    make_game(host=None),
])
def test_other_games_are_not_listed(game):
    assert not is_public_lobby(game)


@pytest.mark.parametrize("game", [
    make_game(state=GameState.LIVE),
    make_game(state=GameState.LIVE, game_type=GameType.COOP),
    make_game(state=GameState.LIVE, game_type=GameType.MATCHMAKER),
    # Match found: the players' games are starting
    make_game(state=GameState.LOBBY, game_type=GameType.MATCHMAKER),
])
def test_live_game_is_listed(game):
    assert is_live_game(game)


@pytest.mark.parametrize("game", [
    make_game(),
    make_game(state=GameState.INITIALIZING, game_type=GameType.MATCHMAKER),
    make_game(state=GameState.ENDED, game_type=GameType.MATCHMAKER),
    make_game(state=GameState.LIVE, visibility=VisibilityState.FRIENDS),
    make_game(state=GameState.LIVE, host=None),
])
def test_other_games_are_not_live(game):
    assert not is_live_game(game)


def test_live_game_dict_has_only_live_fields():
    info = live_game_dict(make_game(state=GameState.LIVE, launched_at=1762812000.5))

    assert tuple(info) == LIVE_GAME_FIELDS
    assert info["launched_at"] == 1762812000.5
    for private in ("command", "visibility", "map_file_path", "teams_ids"):
        assert private not in info


def test_public_game_dict_has_only_public_fields():
    info = public_game_dict(make_game())

    assert tuple(info) == PUBLIC_GAME_FIELDS
    for private in ("command", "visibility", "map_file_path", "teams_ids", "launched_at"):
        assert private not in info


def make_queue(name="ladder1v1", running=True, boundaries=((1000, 1400),)):
    queue = mock.Mock()
    queue.is_running = running
    queue.to_dict.return_value = {
        "queue_name": name,
        "queue_pop_time": "2026-11-11T10:00:30+00:00",
        "queue_pop_time_delta": 12.5,
        "num_players": len(boundaries),
        "boundary_80s": [list(b) for b in boundaries],
        "boundary_75s": [list(b) for b in boundaries],
        "team_size": 1,
    }
    return queue


def test_public_queue_dict_has_only_public_fields():
    queue = make_queue()
    queue.to_dict.return_value["something_new"] = "private"

    info = public_queue_dict(queue)

    assert tuple(info) == PUBLIC_QUEUE_FIELDS
    assert info["num_players"] == 1


@pytest.fixture
async def public_server(unused_tcp_port):
    game_service = mock.Mock()
    game_service.all_games = []
    ladder_service = mock.Mock()
    ladder_service.queues = {}
    lobby_server = mock.Mock(services={
        "game_service": game_service,
        "ladder_service": ladder_service,
    })

    server = PublicServer(lobby_server)
    await server.start("127.0.0.1", unused_tcp_port)

    yield server

    await server.shutdown()


async def get_games(server, path="/games"):
    url = f"http://{server.host}:{server.port}{path}"
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        async with session.get(url) as resp:
            return resp.headers, await resp.json()


async def test_games_lists_public_lobbies_and_live_games(public_server):
    lobby = make_game(uid=1)
    live = make_game(uid=3, state=GameState.LIVE, launched_at=1762812000.5)
    matched = make_game(uid=4, game_type=GameType.MATCHMAKER)
    public_server.game_service.all_games = [
        lobby,
        make_game(uid=2, visibility=VisibilityState.FRIENDS),
        live,
        matched,
        make_game(uid=5, state=GameState.LIVE, visibility=VisibilityState.FRIENDS),
    ]

    headers, data = await get_games(public_server)

    teams = {"teams": {"1": ["Paula_Bean"]}}
    assert data == {
        "games": [public_game_dict(lobby) | teams],
        "live": [live_game_dict(live) | teams, live_game_dict(matched) | teams],
    }
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Cache-Control"].startswith("public, max-age=")


async def test_games_list_is_served_from_cache(public_server):
    with mock.patch.object(config, "PUBLIC_SERVER_CACHE_SECONDS", 60):
        _, first = await get_games(public_server)
        public_server.game_service.all_games = [make_game()]
        _, second = await get_games(public_server)

    assert first == second == {"games": [], "live": []}


async def test_games_list_refreshes_after_cache_expires(public_server):
    with mock.patch.object(config, "PUBLIC_SERVER_CACHE_SECONDS", 0):
        _, first = await get_games(public_server)
        public_server.game_service.all_games = [make_game()]
        _, second = await get_games(public_server)

    assert first == {"games": [], "live": []}
    assert [game["uid"] for game in second["games"]] == [1]


async def test_matchmaker_lists_running_queues(public_server):
    public_server.ladder_service.queues = {
        "ladder1v1": make_queue("ladder1v1", boundaries=((1000, 1400), (1500, 1900))),
        "tmm2v2": make_queue("tmm2v2"),
        "paused": make_queue("paused", running=False),
    }

    headers, data = await get_games(public_server, "/matchmaker")

    assert [queue["queue_name"] for queue in data["queues"]] == ["ladder1v1", "tmm2v2"]
    assert data["queues"][0]["num_players"] == 2
    assert data["queues"][0]["boundary_75s"] == [[1000, 1400], [1500, 1900]]
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Cache-Control"].startswith("public, max-age=")


async def test_routes_are_cached_separately(public_server):
    with mock.patch.object(config, "PUBLIC_SERVER_CACHE_SECONDS", 60):
        _, games = await get_games(public_server)
        public_server.ladder_service.queues = {"ladder1v1": make_queue()}
        _, queues = await get_games(public_server, "/matchmaker")

    assert games == {"games": [], "live": []}
    assert [queue["queue_name"] for queue in queues["queues"]] == ["ladder1v1"]
