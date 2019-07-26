import asyncio
from time import time

import jwt
import pytest
from server import VisibilityState
from tests import API_PRIV_KEY

from .conftest import (connect_and_sign_in, connect_client, perform_login,
                       read_until, read_until_command)
from .testclient import ClientTest

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


async def test_server_invalid_login(loop, lobby_server):
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


async def test_server_ban(loop, lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ('Dostya', 'vodka'))
    msg = await proto.read_message()
    assert msg == {
        'command': 'notice',
        'style': 'error',
        'text': 'You are banned from FAF for 981 years.\n Reason :\n Test permanent ban'}
    proto.close()


async def test_server_valid_login(loop, lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ('test', 'test_password'))
    msg = await proto.read_message()
    assert msg == {
        'command': 'welcome',
        'me': {
            'clan': '678',
            'country': '',
            'global_rating': [2000.0, 125.0],
            'id': 1,
            'ladder_rating': [2000.0, 125.0],
            'login': 'test',
            'number_of_games': 5
        },
        'id': 1,
        'login': 'test'
    }
    lobby_server.close()
    proto.close()
    await lobby_server.wait_closed()


async def test_server_valid_login_with_token(lobby_server):
    proto = await connect_client(lobby_server)
    proto.send_message({
        'command': 'auth',
        'version': '1.0.0-dev',
        'user_agent': 'faf-client',
        'token': jwt.encode({
          "user_id": 1,
          "user_name": "test",
          "scope": [],
          "exp": int(time() + 10),
          "authorities": [],
          "non_locked": True,
          "jti": "",
          "client_id": ""
        }, API_PRIV_KEY, algorithm='RS256').decode(),
        'unique_id': 'some_id'
    })
    await proto.drain()

    msg = await proto.read_message()
    assert msg['command'] == 'irc_password'
    msg = await proto.read_message()
    assert msg == {
        'command': 'welcome',
        'me': {
            'clan': '678',
            'country': '',
            'global_rating': [2000.0, 125.0],
            'id': 1,
            'ladder_rating': [2000.0, 125.0],
            'login': 'test',
            'number_of_games': 5
        },
        'id': 1,
        'login': 'test'
    }
    lobby_server.close()
    proto.close()
    await lobby_server.wait_closed()


async def test_server_login_expired_token(lobby_server):
    proto = await connect_client(lobby_server)
    proto.send_message({
        'command': 'auth',
        'version': '1.0.0-dev',
        'user_agent': 'faf-client',
        'token': jwt.encode({
            "user_id": 1,
            "user_name": "test",
            "exp": int(time() - 10)
        }, API_PRIV_KEY, algorithm='RS256').decode(),
        'unique_id': 'some_id'
    })
    await proto.drain()

    msg = await proto.read_message()
    assert msg == {
        'command': 'authentication_failed',
        'text': 'Token signature was invalid'
    }
    lobby_server.close()
    proto.close()
    await lobby_server.wait_closed()


async def test_server_login_malformed_token(lobby_server):
    """This scenario could only happen if the API somehow signed a token that
    was missing critical data"""
    proto = await connect_client(lobby_server)
    proto.send_message({
        'command': 'auth',
        'version': '1.0.0-dev',
        'user_agent': 'faf-client',
        'token': jwt.encode(
            {"exp": int(time() + 10)}, API_PRIV_KEY, algorithm='RS256'
        ).decode(),
        'unique_id': 'some_id'
    })
    await proto.drain()

    msg = await proto.read_message()
    assert msg == {
        'command': 'authentication_failed',
        'text': 'Token signature was invalid'
    }
    lobby_server.close()
    proto.close()
    await lobby_server.wait_closed()


async def test_server_double_login(loop, lobby_server):
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


async def test_server_invalid_command(lobby_server):
    proto = await connect_client(lobby_server)
    await perform_login(proto, ('test', 'test_password'))
    proto.send_message({'command': 'this_is_an_invalid_command'})
    await proto.drain()
    msg = await read_until_command(proto, 'invalid')

    assert msg == {'command': 'invalid'}


async def test_player_info_broadcast(loop, lobby_server):
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
async def test_info_broadcast_authenticated(loop, lobby_server):
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


async def test_non_ice_client(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )

    await read_until(proto, lambda msg: msg['command'] == 'game_info')

    proto.send_message({
        'command': 'InitiateTest',
        'target': 'connectivity'
    })
    await proto.drain()
    msg = await proto.read_message()

    assert msg == {
        'command': 'notice',
        'style': 'error',
        'text': 'Your client version is no longer supported. Please update to the newest version: https://faforever.com'
    }


async def test_registration_deprecated(lobby_server):
    proto = await connect_client(lobby_server)
    
    proto.send_message({'command': 'create_account'})
    await proto.drain()
    msg = await proto.read_message()

    assert msg == {
        'command': 'notice',
        'style': 'error',
        'text': 'FAF no longer supports direct registration. Please use the website to register.'
    }


async def test_host_missing_fields(loop, lobby_server, player_service):
    player_id, session, proto = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )

    await read_until(proto, lambda msg: msg['command'] == 'game_info')

    proto.send_message({
        'command': 'game_host',
        'mod': '',
        'visibility': VisibilityState.to_string(VisibilityState.PUBLIC),
        'title': ''
    })
    await proto.drain()

    msg = await read_until(proto, lambda msg: msg['command'] == 'game_info')

    assert msg['title'] == 'test&#x27;s game'
    assert msg['mapname'] == 'scmp_007'
    assert msg['map_file_path'] == 'maps/scmp_007.zip'
    assert msg['featured_mod'] == 'faf'
