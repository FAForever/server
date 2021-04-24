import pytest

from .conftest import (
    connect_and_sign_in,
    connect_client,
    perform_login,
    read_until_command
)

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def test_server_invalid_login(lobby_server):
    proto = await connect_client(lobby_server)
    # Try a user that doesn't exist
    await perform_login(proto, ("Cat", "epic"))
    auth_failed_msg = {
        "command": "authentication_failed",
        "text": "Login not found or password incorrect. They are case sensitive."
    }
    msg = await proto.read_message()
    assert msg == auth_failed_msg

    # Try a user that exists, but use the wrong password
    await perform_login(proto, ("test", "epic"))
    msg = await proto.read_message()
    assert msg == auth_failed_msg


@pytest.mark.parametrize("user", [
    ("Dostya", "vodka"),
    ("ban_long_time", "ban_long_time")
])
async def test_server_ban(lobby_server, user):
    proto = await connect_client(lobby_server)
    await perform_login(proto, user)
    msg = await proto.read_message()
    assert msg == {
        "command": "notice",
        "style": "error",
        "text": "You are banned from FAF forever. <br>Reason: <br>Test permanent ban"
    }


@pytest.mark.parametrize("user", ["ban_revoked", "ban_expired"])
async def test_server_ban_revoked_or_expired(lobby_server, user):
    proto = await connect_client(lobby_server)
    await perform_login(proto, (user, user))
    msg = await proto.read_message()

    assert msg["command"] == "welcome"
    assert msg["login"] == user


async def test_server_valid_login(lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ("Rhiza", "puff_the_magic_dragon"))
    msg = await proto.read_message()
    me = {
        "id": 3,
        "login": "Rhiza",
        "clan": "123",
        "country": "",
        "ratings": {
            "global": {
                "rating": [1650.0, 62.52],
                "number_of_games": 2
            },
            "ladder_1v1": {
                "rating": [1650.0, 62.52],
                "number_of_games": 2
            }
        },
        "global_rating": [1650.0, 62.52],
        "ladder_rating": [1650.0, 62.52],
        "number_of_games": 2
    }
    assert msg == {
        "command": "welcome",
        "me": me,
        "id": 3,
        "login": "Rhiza"
    }
    msg = await proto.read_message()
    assert msg == {
        "command": "player_info",
        "players": [me]
    }
    msg = await proto.read_message()
    assert msg == {
        "command": "social",
        "autojoin": ["#123_clan"],
        "channels": ["#123_clan"],
        "friends": [],
        "foes": [],
        "power": 0
    }


async def test_server_valid_login_admin(lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ("test", "test_password"))
    msg = await proto.read_message()
    me = {
        "id": 1,
        "login": "test",
        "clan": "678",
        "country": "",
        "ratings": {
            "global": {
                "rating": [2000.0, 125.0],
                "number_of_games": 5
            },
            "ladder_1v1": {
                "rating": [2000.0, 125.0],
                "number_of_games": 5
            }
        },
        "global_rating": [2000.0, 125.0],
        "ladder_rating": [2000.0, 125.0],
        "number_of_games": 5,
    }
    assert msg == {
        "command": "welcome",
        "me": me,
        "id": 1,
        "login": "test"
    }
    msg = await proto.read_message()
    assert msg == {
        "command": "player_info",
        "players": [me]
    }
    msg = await proto.read_message()
    assert msg == {
        "command": "social",
        "autojoin": ["#678_clan"],
        "channels": ["#678_clan"],
        "friends": [],
        "foes": [3],
        "power": 2
    }


async def test_server_valid_login_moderator(lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ("moderator", "moderator"))
    msg = await proto.read_message()
    me = {
        "id": 20,
        "login": "moderator",
        "country": "",
        "ratings": {
            "global": {
                "rating": [1500, 500],
                "number_of_games": 0
            },
            "ladder_1v1": {
                "rating": [1500, 500],
                "number_of_games": 0
            }
        },
        "global_rating": [1500, 500],
        "ladder_rating": [1500, 500],
        "number_of_games": 0
    }
    assert msg == {
        "command": "welcome",
        "me": me,
        "id": 20,
        "login": "moderator"
    }
    msg = await proto.read_message()
    assert msg == {
        "command": "player_info",
        "players": [me]
    }
    msg = await proto.read_message()
    assert msg == {
        "command": "social",
        "autojoin": ["#moderators"],
        "channels": ["#moderators"],
        "friends": [],
        "foes": [],
        "power": 1
    }


@pytest.mark.parametrize("user", [
    ("test", "test_password"),
    ("ban_revoked", "ban_revoked"),
    ("ban_expired", "ban_expired"),
    ("No_UID", "his_pw"),
    ("steam_id", "steam_id")
])
async def test_policy_server_contacted(lobby_server, policy_server, player_service, user):
    player_service.is_uniqueid_exempt = lambda _: False

    _, _, proto = await connect_and_sign_in(user, lobby_server)
    await read_until_command(proto, "game_info")

    policy_server.verify.assert_called_once()


async def test_server_double_login(lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ("test", "test_password"))
    msg = await proto.read_message()
    msg["command"] == "welcome"

    # Sign in again with a new protocol object
    proto2 = await connect_client(lobby_server)
    await perform_login(proto2, ("test", "test_password"))
    msg = await proto2.read_message()
    msg["command"] == "welcome"

    msg = await read_until_command(proto, "notice")
    assert msg == {
        "command": "notice",
        "style": "error",
        "text": "You have been signed out because you signed in elsewhere."
    }
