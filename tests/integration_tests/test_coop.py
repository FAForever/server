import datetime

from sqlalchemy import select

from server.db.models import coop_leaderboard
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until, read_until_command
from .test_game import host_game, send_player_options


@fast_forward(5)
async def test_host_coop_game(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ("test", "test_password"),
        lobby_server
    )

    await read_until_command(proto, "game_info")

    await host_game(proto, mod="coop", title="")

    msg = await read_until_command(proto, "game_info")

    assert msg["title"] == "test's game"
    assert msg["mapname"] == "scmp_007"
    assert msg["map_file_path"] == "maps/scmp_007.zip"
    assert msg["featured_mod"] == "coop"
    assert msg["game_type"] == "coop"


@fast_forward(30)
async def test_single_player_game_recorded(lobby_server, database):
    test_id, _, proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await read_until_command(proto, "game_info")

    # Set up the game
    game_id = await host_game(proto, mod="coop", mapname="scmp_coop_123.v0002")
    # Set player options
    await send_player_options(
        proto,
        [test_id, "Army", 1],
        [test_id, "Team", 1],
        [test_id, "StartSpot", 1],
        [test_id, "Faction", 1],
        [test_id, "Color", 1],
    )

    # Launch game
    await proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    await read_until(
        proto,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )

    # End the game
    # Single player coop won't report any results

    await proto.send_message({
        "target": "game",
        "command": "GameEnded",
        "args": []
    })

    await proto.send_message({
        "target": "game",
        "command": "OperationComplete",
        "args": [1, 0, "00:11:50"]
    })

    # Now disconnect
    await proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Ended"]
    })

    await read_until_command(proto, "game_info", uid=game_id, state="closed")

    async with database.acquire() as conn:
        result = await conn.execute(
            select([coop_leaderboard]).where(
                coop_leaderboard.c.gameuid == game_id
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row.secondary == 0
        assert row.time == datetime.time(0, 11, 50)
        assert row.player_count == 1
