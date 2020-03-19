import pytest

from .conftest import (
    connect_and_sign_in, connect_client, perform_login, read_until_command
)

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def test_server_invalid_login(lobby_server):
    proto = await connect_client(lobby_server)
    # Try a user that doesn't exist
    await perform_login(proto, ('Cat', 'epic'))
    auth_failed_msg = {
        'command': 'authentication_failed',
        'context': 'denied'
    }
    msg = await proto.read_message()
    assert msg == auth_failed_msg

    # Try a user that exists, but use the wrong password
    await perform_login(proto, ('test', 'epic'))
    msg = await proto.read_message()
    assert msg == auth_failed_msg

    proto.close()


@pytest.mark.parametrize("user", [
    ("test", "test_password"),
    ("Rhiza", "puff_the_magic_dragon"),
    ("ban_revoked", "ban_revoked")
])
async def test_server_steam_link(lobby_server, mocker, user):
    mocker.patch("server.lobbyconnection.config.FORCE_STEAM_LINK", True)
    mocker.patch("server.lobbyconnection.config.FORCE_STEAM_LINK_AFTER_DATE", 0)

    proto = await connect_client(lobby_server)

    await perform_login(proto, user)
    auth_failed_msg = {
        'command': 'authentication_failed',
        'context': 'steam_link'
    }
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
