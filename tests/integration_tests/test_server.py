import asyncio
import contextlib

import pytest
from sqlalchemy import and_, select

from server.db.models import avatars, avatars_list, ban
from tests.utils import fast_forward

from .conftest import (
    connect_and_sign_in,
    connect_client,
    connect_mq_consumer,
    perform_login,
    read_until,
    read_until_command
)
from .test_game import host_game, join_game, open_fa, send_player_options

TEST_ADDRESS = ("127.0.0.1", None)


async def test_server_deprecated_client(lobby_server):
    proto = await connect_client(lobby_server)

    await proto.send_message({"command": "ask_session", "user_agent": "faf-client", "version": "0.0.0"})
    msg = await proto.read_message()

    assert msg["command"] == "notice"

    proto = await connect_client(lobby_server)
    await proto.send_message({"command": "ask_session", "version": "0.0.0"})
    msg = await proto.read_message()

    assert msg["command"] == "notice"


async def test_old_client_error(lobby_server):
    error_msg = {
        "command": "notice",
        "style": "error",
        "text": 'Cannot join game. Please update your client to the newest version.'
    }
    player_id, session, proto = await connect_and_sign_in(
        ("test", "test_password"),
        lobby_server
    )

    await read_until_command(proto, "game_info")

    await proto.send_message({
        "command": "InitiateTest",
        "target": "connectivity"
    })
    msg = await proto.read_message()
    assert msg == {
        "command": "notice",
        "style": "error",
        "text": 'Your client version is no longer supported. Please update to the newest version: https://faforever.com'
    }

    await proto.send_message({"command": "game_host"})
    msg = await proto.read_message()
    assert msg == error_msg

    await proto.send_message({"command": "game_join"})
    msg = await proto.read_message()
    assert msg == error_msg

    await proto.send_message({"command": "game_matchmaking", "state": "start"})
    msg = await proto.read_message()
    assert msg == error_msg


@fast_forward(50)
async def test_ping_message(lobby_server):
    _, _, proto = await connect_and_sign_in(("test", "test_password"), lobby_server)

    # We should receive the message every 45 seconds
    await read_until_command(proto, "ping", timeout=46)


@fast_forward(5)
async def test_player_info_broadcast(lobby_server):
    p1 = await connect_client(lobby_server)
    p2 = await connect_client(lobby_server)

    await perform_login(p1, ("test", "test_password"))
    await perform_login(p2, ("Rhiza", "puff_the_magic_dragon"))

    await read_until(
        p2, lambda m: "player_info" in m.values()
        and any(map(lambda d: d["login"] == "test", m["players"]))
    )


@pytest.mark.rabbitmq
@fast_forward(5)
async def test_player_info_broadcast_to_rabbitmq(lobby_server, channel):
    mq_proto = await connect_mq_consumer(
        lobby_server,
        channel,
        "broadcast.playerInfo.update"
    )
    mq_proto_all = await connect_mq_consumer(
        lobby_server,
        channel,
        "broadcast.*.update"
    )

    _, _, proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await read_until_command(proto, "player_info")

    await read_until(
        mq_proto, lambda m: "player_info" in m.values()
        and any(map(lambda d: d["login"] == "test", m["players"]))
    )
    await read_until(
        mq_proto_all, lambda m: "player_info" in m.values()
        and any(map(lambda d: d["login"] == "test", m["players"]))
    )


@fast_forward(5)
async def test_info_broadcast_authenticated(lobby_server):
    proto1 = await connect_client(lobby_server)
    proto2 = await connect_client(lobby_server)
    proto3 = await connect_client(lobby_server)

    await perform_login(proto1, ("test", "test_password"))
    await perform_login(proto2, ("Rhiza", "puff_the_magic_dragon"))
    await proto1.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "mod": "ladder1v1",
        "faction": "uef"
    })
    # Will timeout if the message is never received
    await read_until_command(proto2, "matchmaker_info")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proto3.read_message(), 0.2)
        # Unauthenticated connections should not receive the message
        assert False


@fast_forward(5)
async def test_game_info_not_sent_to_foes(lobby_server):
    _, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await read_until_command(proto1, "game_info")

    await host_game(proto1, title="No Foes Allowed", visibility="public")
    msg = await read_until_command(proto1, "game_info")

    assert msg["featured_mod"] == "faf"
    assert msg["title"] == "No Foes Allowed"
    assert msg["visibility"] == "public"

    _, _, proto2 = await connect_and_sign_in(
        ("foed_by_test", "foe"), lobby_server
    )
    # Check game info sent during login
    msg2 = await read_until_command(proto2, "game_info")
    assert msg2["games"] == []

    # Trigger a game_info message
    await proto1.send_message({
        "target": "game",
        "command": "ClearSlot",
        "args": [2]
    })

    await read_until_command(proto1, "game_info")
    # Foe should not see the update
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(proto2, "game_info", timeout=1)


@fast_forward(10)
async def test_game_info_sent_to_friends(lobby_server):
    # test is the friend of friends
    _, _, proto1 = await connect_and_sign_in(
        ("friends", "friends"), lobby_server
    )
    await read_until_command(proto1, "game_info")

    await host_game(proto1, title="Friends Only", visibility="friends")

    # Host should see their own game
    msg = await read_until_command(proto1, "game_info", state="open")
    assert msg["featured_mod"] == "faf"
    assert msg["title"] == "Friends Only"
    assert msg["visibility"] == "friends"

    _, _, proto2 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    _, _, proto3 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    # Check game info sent during login
    msg2 = await read_until_command(proto2, "game_info")
    msg3 = await read_until_command(proto3, "game_info")

    # The hosts friend should see the game
    assert msg2["games"]
    assert msg2["games"][0] == msg

    # However, the other person should not
    assert msg3["games"] == []

    # Trigger a game_info message
    await proto1.send_message({
        "target": "game",
        "command": "ClearSlot",
        "args": [2]
    })

    # The hosts friend should see the update
    await read_until_command(proto2, "game_info")

    # However, the other person should not
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(proto3, "game_info", timeout=1)


@pytest.mark.parametrize("limit", (
    (None, 1000),
    (1500, 1700),
    (1500, None),
))
@fast_forward(5)
async def test_game_info_not_broadcast_out_of_rating_range(lobby_server, limit):
    # Rhiza has displayed rating of 1462
    _, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    _, _, proto2 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(proto1, "game_info")
    await read_until_command(proto2, "game_info")

    await proto1.send_message({
        "command": "game_host",
        "title": "No noobs!",
        "mod": "faf",
        "visibility": "public",
        "rating_min": limit[0],
        "rating_max": limit[1],
        "enforce_rating_range": True
    })

    msg = await read_until_command(proto1, "game_info")

    assert msg["featured_mod"] == "faf"
    assert msg["title"] == "No noobs!"
    assert msg["visibility"] == "public"

    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(proto2, "game_info", timeout=1)


@fast_forward(10)
async def test_game_info_broadcast_to_players_in_lobby(lobby_server):
    # test is the friend of friends
    friends_id, _, proto1 = await connect_and_sign_in(
        ("friends", "friends"), lobby_server
    )
    test_id, _, proto2 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await read_until_command(proto1, "game_info")
    await read_until_command(proto2, "game_info")

    await proto1.send_message({
        "command": "game_host",
        "title": "Friends Only",
        "mod": "faf",
        "visibility": "friends"
    })

    # The host and his friend should see the game
    await read_until_command(proto1, "game_info", teams={})
    await read_until_command(proto2, "game_info", teams={})
    # The host joins which changes the lobby state
    await open_fa(proto1)
    await send_player_options(
        proto1,
        [friends_id, "Army", 1],
        [friends_id, "Team", 1],
    )
    msg = await read_until_command(proto1, "game_info", teams={"1": ["friends"]})
    msg2 = await read_until_command(proto2, "game_info", teams={"1": ["friends"]})

    assert msg == msg2
    assert msg["featured_mod"] == "faf"
    assert msg["title"] == "Friends Only"
    assert msg["visibility"] == "friends"
    assert msg["state"] == "open"

    game_id = msg["uid"]
    await join_game(proto2, game_id)

    await read_until_command(proto1, "game_info", teams={"1": ["friends"]})
    await read_until_command(proto2, "game_info", teams={"1": ["friends"]})
    await send_player_options(proto1, [test_id, "Army", 1], [test_id, "Team", 1])
    await read_until_command(proto1, "game_info", teams={"1": ["friends", "test"]})
    await read_until_command(proto2, "game_info", teams={"1": ["friends", "test"]})

    # Now we unfriend the person in the lobby
    await proto1.send_message({
        "command": "social_remove",
        "friend": test_id
    })
    # And change some game options to trigger a new update message
    await proto1.send_message({
        "target": "game",
        "command": "GameOption",
        "args": ["Title", "New Title"]
    })

    # The host and the other player in the lobby should see the game even
    # though they are not friends anymore
    msg = await read_until_command(proto1, "game_info", timeout=5)
    msg2 = await read_until_command(proto2, "game_info", timeout=5)

    assert msg == msg2
    assert msg["featured_mod"] == "faf"
    assert msg["title"] == "New Title"
    assert msg["visibility"] == "friends"


@pytest.mark.rabbitmq
@fast_forward(10)
async def test_info_broadcast_to_rabbitmq(lobby_server, channel):
    mq_proto_all = await connect_mq_consumer(
        lobby_server,
        channel,
        "broadcast.*.update"
    )

    _, _, proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await read_until_command(proto, "game_info")
    # matchmaker_info is broadcast whenever the timer pops
    await read_until_command(mq_proto_all, "matchmaker_info")

    # Check that game_info is broadcast when a new game is hosted
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(mq_proto_all, "game_info", timeout=3)

    await host_game(proto)
    await read_until_command(mq_proto_all, "game_info")


@pytest.mark.parametrize("user", [
    ("test", "test_password"),
    ("ban_revoked", "ban_revoked"),
    ("ban_expired", "ban_expired"),
    ("No_UID", "his_pw")
])
async def test_game_host_authenticated(lobby_server, user):
    _, _, proto = await connect_and_sign_in(user, lobby_server)
    await read_until_command(proto, "game_info")

    await proto.send_message({
        "command": "game_host",
        "title": "My Game",
        "mod": "faf",
        "visibility": "public",
    })

    msg = await read_until_command(proto, "game_launch")

    assert msg["mod"] == "faf"
    assert "args" in msg
    assert isinstance(msg["uid"], int)


@fast_forward(5)
async def test_host_missing_fields(event_loop, lobby_server, player_service):
    player_id, session, proto = await connect_and_sign_in(
        ("test", "test_password"),
        lobby_server
    )

    await read_until_command(proto, "game_info")

    await proto.send_message({
        "command": "game_host",
        "mod": "",
        "visibility": "public",
        "title": ""
    })

    msg = await read_until_command(proto, "game_info")

    assert msg["title"] == "test's game"
    assert msg["game_type"] == "custom"
    assert msg["mapname"] == "scmp_007"
    assert msg["map_file_path"] == "maps/scmp_007.zip"
    assert msg["featured_mod"] == "faf"


async def test_play_game_while_queueing(lobby_server):
    player_id, session, proto = await connect_and_sign_in(
        ("test", "test_password"),
        lobby_server
    )

    await read_until_command(proto, "game_info")

    await proto.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "faction": "uef"
    })

    await proto.send_message({"command": "game_host"})
    msg = await read_until_command(proto, "notice")
    assert msg == {
        "command": "notice",
        "style": "error",
        "text": "Can't host a game while in state SEARCHING_LADDER"
    }

    await proto.send_message({"command": "game_join"})
    msg = await read_until_command(proto, "notice")
    assert msg == {
        "command": "notice",
        "style": "error",
        "text": "Can't join a game while in state SEARCHING_LADDER"
    }


@pytest.mark.parametrize("command", ["game_host", "game_join"])
async def test_server_ban_prevents_hosting(lobby_server, database, command):
    """
    Players who are banned while they are online, should immediately be
    prevented from joining or hosting games until their ban expires.
    """
    player_id, _, proto = await connect_and_sign_in(
        ("banme", "banme"), lobby_server
    )
    # User successfully logs in
    await read_until_command(proto, "game_info")

    async with database.acquire() as conn:
        await conn.execute(
            ban.insert().values(
                player_id=player_id,
                author_id=player_id,
                reason="Test live ban",
                expires_at=None,
                level="GLOBAL"
            )
        )

    await proto.send_message({"command": command})

    msg = await proto.read_message()
    assert msg == {
        "command": "notice",
        "style": "error",
        "text": "You are banned from FAF forever. <br>Reason: <br>Test live ban"
    }


@fast_forward(5)
async def test_coop_list(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ("test", "test_password"),
        lobby_server
    )

    await read_until_command(proto, "game_info")

    await proto.send_message({"command": "coop_list"})

    msg = await read_until_command(proto, "coop_info")
    assert "name" in msg
    assert "description" in msg
    assert "filename" in msg


async def test_ice_servers_empty(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ("test", "test_password"),
        lobby_server
    )

    await read_until_command(proto, "game_info")

    await proto.send_message({"command": "ice_servers"})

    msg = await read_until_command(proto, "ice_servers")

    # By default the server config should not have any ice servers
    assert msg == {
        "command": "ice_servers",
        "ice_servers": [],
        "ttl": 86400
    }


async def get_player_selected_avatars(conn, player_id):
    return await conn.execute(
        select([avatars.c.id, avatars_list.c.url])
        .select_from(avatars_list.join(avatars))
        .where(
            and_(
                avatars.c.idUser == player_id,
                avatars.c.selected == 1,
            )
        )
    )


@fast_forward(30)
async def test_avatar_list_empty(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ("test", "test_password"),
        lobby_server
    )
    await read_until_command(proto, "game_info")

    await proto.send_message({
        "command": "avatar", "action": "list_avatar"
    })
    msg = await read_until_command(proto, "avatar")

    assert msg == {
        "command": "avatar",
        "avatarlist": []
    }


@fast_forward(30)
async def test_avatar_select(lobby_server, database):
    # This user has multiple avatars in the test data
    player_id, _, proto = await connect_and_sign_in(
        ("player_service1", "player_service1"),
        lobby_server
    )
    await read_until_command(proto, "game_info")
    # Skip any latent player broadcasts
    with contextlib.suppress(asyncio.TimeoutError):
        await read_until_command(proto, "player_info", timeout=5)

    await proto.send_message({
        "command": "avatar", "action": "list_avatar"
    })

    msg = await read_until_command(proto, "avatar")
    avatar_list = msg["avatarlist"]

    for avatar in avatar_list:
        await proto.send_message({
            "command": "avatar",
            "action": "select",
            "avatar": avatar["url"]
        })
        msg = await read_until_command(proto, "player_info")
        assert msg["players"][0]["avatar"] == avatar

    async with database.acquire() as conn:
        result = await get_player_selected_avatars(conn, player_id)
        assert result.rowcount == 1
        row = result.fetchone()
        assert row.url == avatar["url"]

    await proto.send_message({
        "command": "avatar",
        "action": "select",
        "avatar": "BOGUS!"
    })
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(proto, "player_info", timeout=10)

    async with database.acquire() as conn:
        result = await get_player_selected_avatars(conn, player_id)
        assert result.rowcount == 1
        row = result.fetchone()
        assert row.url == avatar["url"]


@fast_forward(30)
async def test_avatar_select_not_owned(lobby_server, database):
    # This user has no avatars
    player_id, _, proto = await connect_and_sign_in(
        ("test", "test_password"),
        lobby_server
    )
    await read_until_command(proto, "game_info")
    # Skip any latent player broadcasts
    with contextlib.suppress(asyncio.TimeoutError):
        await read_until_command(proto, "player_info", timeout=5)

    await proto.send_message({
        "command": "avatar",
        "action": "select",
        "avatar": "https://content.faforever.com/faf/avatars/UEF.png"
    })
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(proto, "player_info", timeout=10)

    async with database.acquire() as conn:
        result = await get_player_selected_avatars(conn, player_id)
        assert result.rowcount == 0
