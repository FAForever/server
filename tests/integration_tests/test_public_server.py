import aiohttp

from server.public import (
    PUBLIC_GAME_FIELDS,
    PUBLIC_QUEUE_FIELDS,
    public_game_dict
)
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command
from .test_game import (
    open_fa,
    queue_players_for_matchmaking,
    send_player_options,
    start_search
)


def listify(obj: dict):
    for k, v in obj.items():
        if isinstance(v, tuple):
            obj[k] = list(v)
        elif isinstance(v, dict):
            obj[k] = listify(v)
    return obj


async def host_lobby(lobby_server, credentials, visibility):
    player_id, _, proto = await connect_and_sign_in(credentials, lobby_server)
    await proto.send_message({
        "command": "game_host",
        "mod": "faf",
        "visibility": visibility
    })
    msg = await read_until_command(proto, "game_launch")
    await proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Idle"]
    })
    await proto.send_message({
        "target": "game",
        "command": "PlayerOption",
        # Send this as a string because json object keys can only be strings.
        # This makes our assertion check easier.
        "args": [player_id, "Team", "1"]
    })
    return msg["uid"]


async def get_public_games(public_server, path="/games"):
    url = f"http://{public_server.host}:{public_server.port}{path}"
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        async with session.get(url) as resp:
            return await resp.json()


@fast_forward(2)
async def test_public_lobby_is_listed(public_server, lobby_server, game_service):
    game_id = await host_lobby(lobby_server, ("test", "test_password"), "public")

    data = await get_public_games(public_server)

    assert data == {
        "games": [listify(public_game_dict(game_service[game_id]))],
        "live": [],
    }
    assert tuple(data["games"][0]) == PUBLIC_GAME_FIELDS


@fast_forward(2)
async def test_friends_only_lobby_is_not_listed(public_server, lobby_server):
    await host_lobby(lobby_server, ("test", "test_password"), "friends")

    data = await get_public_games(public_server)

    assert data == {"games": [], "live": []}


@fast_forward(15)
async def test_matchmaker_game_is_live_once_match_is_found(public_server, lobby_server):
    host_id, host, _, _ = await queue_players_for_matchmaking(lobby_server)

    # The host's game opens and reports its slot, as FA does
    msg = await read_until_command(host, "game_launch")
    await open_fa(host)
    await read_until_command(host, "game_info")
    await send_player_options(
        host,
        (host_id, "StartSpot", msg["map_position"]),
        (host_id, "Army", msg["map_position"]),
        (host_id, "Faction", msg["faction"]),
        (host_id, "Color", msg["map_position"]),
    )
    await read_until_command(host, "game_info")

    data = await get_public_games(public_server)

    assert data["games"] == []
    live = [game for game in data["live"] if game["uid"] == msg["uid"]]
    assert len(live) == 1
    assert live[0]["game_type"] == "matchmaker"
    assert live[0]["host"] == "ladder1"
    assert "ladder1" in [
        name for team in live[0]["teams"].values() for name in team
    ]


@fast_forward(10)
async def test_matchmaker_queues_are_listed(public_server, lobby_server):
    _, _, proto = await connect_and_sign_in(("ladder1", "ladder1"), lobby_server)
    await read_until_command(proto, "game_info")
    await start_search(proto, "ladder1v1")

    data = await get_public_games(public_server, "/matchmaker")

    queues = {queue["queue_name"]: queue for queue in data["queues"]}
    assert "ladder1v1" in queues
    assert queues["ladder1v1"]["num_players"] == 1
    assert len(queues["ladder1v1"]["boundary_75s"]) == 1
    assert tuple(queues["ladder1v1"]) == PUBLIC_QUEUE_FIELDS
