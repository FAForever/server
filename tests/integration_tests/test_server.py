import asyncio
from unittest import mock

import pytest
from server import VisibilityState
from server.db.models import ban

from .conftest import (
    connect_and_sign_in, connect_client, perform_login, read_until,
    read_until_command
)

pytestmark = pytest.mark.asyncio
TEST_ADDRESS = ('127.0.0.1', None)


async def test_server_deprecated_client(lobby_server):
    proto = await connect_client(lobby_server)

    proto.send_message({'command': 'ask_session', 'user_agent': 'faf-client', 'version': '0.0.0'})
    await proto.drain()
    msg = await proto.read_message()

    assert msg['command'] == 'notice'

    proto = await connect_client(lobby_server)
    proto.send_message({'command': 'ask_session', 'version': '0.0.0'})
    await proto.drain()
    msg = await proto.read_message()

    assert msg['command'] == 'notice'


async def test_server_invalid_login(lobby_server):
    proto = await connect_client(lobby_server)
    # Try a user that doesn't exist
    await perform_login(proto, ('Cat', 'epic'))
    auth_failed_msg = {
        'command': 'authentication_failed',
        'text': 'Login not found or password incorrect. They are case sensitive.'
    }
    msg = await proto.read_message()
    assert msg == auth_failed_msg

    # Try a user that exists, but use the wrong password
    await perform_login(proto, ('test', 'epic'))
    msg = await proto.read_message()
    assert msg == auth_failed_msg

    proto.close()


@pytest.mark.parametrize("user", [
    ("Dostya", "vodka"),
    ("ban_long_time", "ban_long_time")
])
async def test_server_ban(lobby_server, user):
    proto = await connect_client(lobby_server)
    await perform_login(proto, user)
    msg = await proto.read_message()
    assert msg == {
        'command': 'notice',
        'style': 'error',
        'text': 'You are banned from FAF forever.\n Reason :\n Test permanent ban'}
    proto.close()


@pytest.mark.parametrize('user', ['ban_revoked', 'ban_expired'])
async def test_server_ban_revoked_or_expired(lobby_server, user):
    proto = await connect_client(lobby_server)
    await perform_login(proto, (user, user))
    msg = await proto.read_message()

    assert msg["command"] == "welcome"
    assert msg["login"] == user


async def test_server_valid_login(lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ('test', 'test_password'))
    msg = await proto.read_message()
    assert msg == {'command': 'welcome',
                   'me': {'clan': '678',
                          'country': '',
                          'global_rating': [2000.0, 125.0],
                          'id': 1,
                          'ladder_rating': [2000.0, 125.0],
                          'login': 'test',
                          'number_of_games': 5},
                   'id': 1,
                   'login': 'test'}


async def test_policy_server_contacted(lobby_server, policy_server, player_service):
    player_service.is_uniqueid_exempt = lambda _: False

    _, _, proto = await connect_and_sign_in(("steam_id", "steam_id"), lobby_server)
    await read_until_command(proto, 'game_info')

    policy_server.verify.assert_called_once()


async def test_server_double_login(lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ('test', 'test_password'))
    msg = await proto.read_message()
    msg['command'] == 'welcome'

    # Sign in again with a new protocol object
    proto2 = await connect_client(lobby_server)
    await perform_login(proto2, ('test', 'test_password'))
    msg = await proto2.read_message()
    msg['command'] == 'welcome'

    msg = await read_until_command(proto, 'notice')
    assert msg == {
        'command': 'notice',
        'style': 'error',
        'text': 'You have been signed out because you signed in elsewhere.'
    }

    lobby_server.close()
    proto.close()
    proto2.close()
    await lobby_server.wait_closed()


async def test_player_info_broadcast(lobby_server):
    p1 = await connect_client(lobby_server)
    p2 = await connect_client(lobby_server)

    await perform_login(p1, ('test', 'test_password'))
    await perform_login(p2, ('Rhiza', 'puff_the_magic_dragon'))

    await read_until(
        p2, lambda m: 'player_info' in m.values()
        and any(map(lambda d: ('login', 'test') in d.items(), m['players']))
    )
    p1.close()
    p2.close()


@pytest.mark.slow
async def test_info_broadcast_authenticated(lobby_server):
    proto1 = await connect_client(lobby_server)
    proto2 = await connect_client(lobby_server)
    proto3 = await connect_client(lobby_server)

    await perform_login(proto1, ('test', 'test_password'))
    await perform_login(proto2, ('Rhiza', 'puff_the_magic_dragon'))
    proto1.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "mod": "ladder1v1",
        "faction": "uef"
    })
    await proto1.drain()
    # Will timeout if the message is never received
    await read_until_command(proto2, "matchmaker_info")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(proto3.read_message(), 0.2)
        # Unauthenticated connections should not receive the message
        assert False


@pytest.mark.parametrize("user", [
    ("test", "test_password"),
    ("ban_revoked", "ban_revoked"),
    ("ban_expired", "ban_expired"),
    ("No_UID", "his_pw"),
    ("steam_id", "steam_id")
])
async def test_game_host_authenticated(lobby_server, user):
    _, _, proto = await connect_and_sign_in(user, lobby_server)
    await read_until_command(proto, 'game_info')

    proto.send_message({
        'command': 'game_host',
        'title': 'My Game',
        'mod': 'faf',
        'visibility': 'public',
    })
    await proto.drain()

    msg = await read_until_command(proto, 'game_launch')

    assert msg['mod'] == 'faf'
    assert 'args' in msg
    assert isinstance(msg['uid'], int)


@pytest.mark.slow
async def test_host_missing_fields(event_loop, lobby_server, player_service):
    player_id, session, proto = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )

    await read_until_command(proto, 'game_info')

    proto.send_message({
        'command': 'game_host',
        'mod': '',
        'visibility': VisibilityState.to_string(VisibilityState.PUBLIC),
        'title': ''
    })
    await proto.drain()

    msg = await read_until_command(proto, 'game_info')

    assert msg['title'] == 'test&#x27;s game'
    assert msg['mapname'] == 'scmp_007'
    assert msg['map_file_path'] == 'maps/scmp_007.zip'
    assert msg['featured_mod'] == 'faf'


async def test_coop_list(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )

    await read_until_command(proto, 'game_info')

    proto.send_message({"command": "coop_list"})
    await proto.drain()

    msg = await read_until_command(proto, "coop_info")
    assert "name" in msg
    assert "description" in msg
    assert "filename" in msg


@pytest.mark.parametrize("command", ["game_host", "game_join"])
async def test_server_ban_prevents_hosting(lobby_server, database, command):
    """
    Players who are banned while they are online, should immediately be
    prevented from joining or hosting games until their ban expires.
    """
    player_id, _, proto = await connect_and_sign_in(
        ('banme', 'banme'), lobby_server
    )
    # User successfully logs in
    await read_until_command(proto, 'game_info')

    async with database.acquire() as conn:
        await conn.execute(
            ban.insert().values(
                player_id=player_id,
                author_id=player_id,
                reason="Test live ban",
                expires_at=None,
                level='GLOBAL'
            )
        )

    proto.send_message({"command": command})
    await proto.drain()

    msg = await proto.read_message()
    assert msg == {
        'command': 'notice',
        'style': 'error',
        'text': 'You are banned from FAF forever.\n Reason :\n Test live ban'
    }
    proto.close()
