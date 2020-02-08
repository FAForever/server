import asyncio
import logging

import pytest
from server.db.models import ban
from tests.utils import fast_forward

from .conftest import (
    connect_and_sign_in, connect_client, perform_login, read_until,
    read_until_command
)

pytestmark = pytest.mark.asyncio
TEST_ADDRESS = ('127.0.0.1', None)


async def test_server_deprecated_client(lobby_server):
    proto = await connect_client(lobby_server)

    await proto.send_message({'command': 'ask_session', 'user_agent': 'faf-client', 'version': '0.0.0'})
    msg = await proto.read_message()

    assert msg['command'] == 'notice'

    proto = await connect_client(lobby_server)
    await proto.send_message({'command': 'ask_session', 'version': '0.0.0'})
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


@fast_forward(50)
async def test_ping_message(lobby_server):
    _, _, proto = await connect_and_sign_in(('test', 'test_password'), lobby_server)

    # We should receive the message every 45 seconds
    await asyncio.wait_for(read_until_command(proto, 'ping'), 46)


async def test_player_info_broadcast(lobby_server):
    p1 = await connect_client(lobby_server)
    p2 = await connect_client(lobby_server)

    await perform_login(p1, ('test', 'test_password'))
    await perform_login(p2, ('Rhiza', 'puff_the_magic_dragon'))

    await read_until(
        p2, lambda m: 'player_info' in m.values()
        and any(map(lambda d: ('login', 'test') in d.items(), m['players']))
    )


@pytest.mark.slow
async def test_info_broadcast_authenticated(lobby_server):
    proto1 = await connect_client(lobby_server)
    proto2 = await connect_client(lobby_server)
    proto3 = await connect_client(lobby_server)

    await perform_login(proto1, ('test', 'test_password'))
    await perform_login(proto2, ('Rhiza', 'puff_the_magic_dragon'))
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


async def test_game_info_not_broadcast_to_foes(lobby_server):
    # Rhiza is foed by test
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
        "title": "No Foes Allowed",
        "mod": "faf",
        "visibility": "public"
    })

    msg = await read_until_command(proto1, "game_info")

    assert msg["featured_mod"] == "faf"
    assert msg["title"] == "No Foes Allowed"
    assert msg["visibility"] == "public"

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(read_until_command(proto2, "game_info"), 0.2)


async def test_game_info_broadcast_to_friends(lobby_server):
    # test is the friend of friends
    _, _, proto1 = await connect_and_sign_in(
        ("friends", "friends"), lobby_server
    )
    _, _, proto2 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    _, _, proto3 = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(proto1, "game_info")
    await read_until_command(proto2, "game_info")
    await read_until_command(proto3, "game_info")

    await proto1.send_message({
        "command": "game_host",
        "title": "Friends Only",
        "mod": "faf",
        "visibility": "friends"
    })

    # The host and his friend should see the game
    msg = await read_until_command(proto1, "game_info")
    msg2 = await read_until_command(proto2, "game_info")

    assert msg == msg2
    assert msg["featured_mod"] == "faf"
    assert msg["title"] == "Friends Only"
    assert msg["visibility"] == "friends"

    # However, the other person should not see the game
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(read_until_command(proto3, "game_info"), 0.2)


@fast_forward(300)
async def test_game_info_broadcast_on_connection_error(
    event_loop, lobby_server, tmp_user, ladder_service, game_service, caplog
):
    """
    Causes connection errors in `do_report_dirties` which in turn will cause
    closed games not to be cleaned up if the errors aren't handled properly.
    """
    # This test causes way to much logging output otherwise
    caplog.set_level(logging.WARNING)

    NUM_HOSTS = 10
    NUM_PLAYERS_DC = 20
    NUM_TIMES_DC = 10

    # Number of times that games will be rehosted
    NUM_GAME_REHOSTS = 20

    # Set up our game hosts
    host_protos = []
    for _ in range(NUM_HOSTS):
        _, _, proto = await connect_and_sign_in(
            await tmp_user("Host"), lobby_server
        )
        host_protos.append(proto)
    await asyncio.gather(*(
        read_until_command(proto, "game_info")
        for proto in host_protos
    ))

    # Set up our players that will disconnect
    dc_players = [await tmp_user("Disconnecter") for _ in range(NUM_PLAYERS_DC)]

    # Host the games
    async def host(proto):
        await proto.send_message({
            "command": "game_host",
            "title": "A dirty game",
            "mod": "faf",
            "visibility": "public"
        })
        msg = await read_until_command(proto, "game_launch")

        # Pretend like ForgedAlliance.exe opened
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Idle"]
        })
        return msg

    async def spam_game_changes(proto):
        for _ in range(NUM_GAME_REHOSTS):
            # Host
            await host(proto)
            await asyncio.sleep(0.1)
            # Leave the game
            await proto.send_message({
                "target": "game",
                "command": "GameState",
                "args": ["Ended"]
            })

    tasks = []
    for proto in host_protos:
        tasks.append(spam_game_changes(proto))

    async def do_dc_player(player):
        for _ in range(NUM_TIMES_DC):
            _, _, proto = await connect_and_sign_in(player, lobby_server)
            await read_until_command(proto, "game_info")
            await asyncio.sleep(0.1)
            proto.close()

    async def do_dc_players():
        await asyncio.gather(*(
            do_dc_player(player)
            for player in dc_players
        ))

    tasks.append(do_dc_players())

    # Let the guests cause a bunch of broadcasts to happen while the other
    # players are disconnecting
    await asyncio.gather(*tasks)

    # Wait for games to be cleaned up
    for proto in host_protos:
        proto.close()
    ladder_service.shutdown_queues()

    # Wait for games to time out if they need to
    await asyncio.sleep(35)

    # Ensure that the connection errors haven't prevented games from being
    # cleaned up.
    assert len(game_service.all_games) == 0


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

    await proto.send_message({
        'command': 'game_host',
        'title': 'My Game',
        'mod': 'faf',
        'visibility': 'public',
    })

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

    await proto.send_message({
        'command': 'game_host',
        'mod': '',
        'visibility': 'public',
        'title': ''
    })

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

    await proto.send_message({"command": "coop_list"})

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

    command_message = {"command": command}
    if command == "game_join":
        command_message["uid"] = 1

    await proto.send_message(command_message)

    msg = await proto.read_message()
    assert msg == {
        'command': 'notice',
        'style': 'error',
        'text': 'You are banned from FAF forever.\n Reason :\n Test live ban'
    }
    proto.close()
