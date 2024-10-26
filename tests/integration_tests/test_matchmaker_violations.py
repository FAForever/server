import asyncio
from datetime import datetime, timezone

import pytest

from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command
from .test_game import (
    client_response,
    open_fa,
    queue_players_for_matchmaking,
    send_player_options,
    start_search
)
from .test_parties import accept_party_invite, invite_to_party
from .test_teammatchmaker import \
    queue_players_for_matchmaking as queue_players_for_matchmaking_2v2


@fast_forward(360)
async def test_violation_for_guest_timeout(mocker, lobby_server):
    mock_now = mocker.patch(
        "server.ladder_service.violation_service.datetime_now",
        return_value=datetime(2022, 2, 5, tzinfo=timezone.utc)
    )
    _, host, guest_id, guest = await queue_players_for_matchmaking(lobby_server)

    # The player that queued last will be the host
    async def launch_game_and_timeout_guest():
        await client_response(host, timeout=60)
        await read_until_command(host, "game_info")

        await read_until_command(guest, "game_launch")
        await read_until_command(guest, "match_cancelled", timeout=120)
        await read_until_command(host, "match_cancelled")
        await host.send_message({
            "command": "GameState",
            "target": "game",
            "args": ["Ended"]
        })

    await launch_game_and_timeout_guest()

    # Second time searching there is no ban
    await start_search(host)
    await start_search(guest)
    await launch_game_and_timeout_guest()

    # Third time searching there is a short ban
    await guest.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": "ladder1v1"
    })

    msg = await read_until_command(guest, "search_timeout")
    assert msg == {
        "command": "search_timeout",
        "timeouts": [{
            "player": guest_id,
            "expires_at": "2022-02-05T00:10:00+00:00"
        }]
    }

    mock_now.return_value = datetime(2022, 2, 5, 0, 10, tzinfo=timezone.utc)
    await asyncio.sleep(1)

    # Third successful search
    await start_search(host)
    await start_search(guest)
    await launch_game_and_timeout_guest()

    # Fourth time searching there is a long ban
    await guest.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": "ladder1v1"
    })

    msg = await read_until_command(guest, "search_timeout")
    assert msg == {
        "command": "search_timeout",
        "timeouts": [{
            "player": guest_id,
            "expires_at": "2022-02-05T00:40:00+00:00"
        }]
    }

    mock_now.return_value = datetime(2022, 2, 5, 0, 40, tzinfo=timezone.utc)
    await asyncio.sleep(1)

    # Fourth successful search
    await start_search(host)
    await start_search(guest)
    await launch_game_and_timeout_guest()

    # Fifth time searching there is a long ban
    await guest.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": "ladder1v1"
    })

    msg = await read_until_command(guest, "search_timeout")
    assert msg == {
        "command": "search_timeout",
        "timeouts": [{
            "player": guest_id,
            "expires_at": "2022-02-05T01:10:00+00:00"
        }]
    }

    msg = await read_until_command(guest, "notice")
    assert msg == {
        "command": "notice",
        "style": "info",
        "text": "Player ladder2 is timed out for 30 minutes"
    }


@fast_forward(360)
async def test_violation_established_peer(mocker, lobby_server):
    mocker.patch(
        "server.ladder_service.violation_service.datetime_now",
        return_value=datetime(2022, 2, 5, tzinfo=timezone.utc)
    )
    protos, ids = await queue_players_for_matchmaking_2v2(lobby_server)
    host, guest1, guest2, guest3 = protos
    host_id, guest1_id, guest2_id, guest3_id = ids

    # Connect all players to the host
    await asyncio.gather(*[
        client_response(proto, timeout=60)
        for proto in protos
    ])
    await send_player_options(
        host,
        [host_id, "Color", 1],
        [guest1_id, "Color", 2],
        [guest2_id, "Color", 3],
        [guest3_id, "Color", 4],
    )

    # Set up connection matrix
    for id in (guest1_id, guest2_id, guest3_id):
        await host.send_message({
            "target": "game",
            "command": "EstablishedPeer",
            "args": [id],
        })
    for id in (host_id, guest2_id):
        await guest1.send_message({
            "target": "game",
            "command": "EstablishedPeer",
            "args": [id],
        })
    for id in (host_id, guest1_id):
        await guest2.send_message({
            "target": "game",
            "command": "EstablishedPeer",
            "args": [id],
        })
    # Guest3 only connects to the host
    await guest3.send_message({
        "target": "game",
        "command": "EstablishedPeer",
        "args": [host_id],
    })

    await read_until_command(host, "match_cancelled", timeout=120)
    msg = await read_until_command(guest3, "search_violation", timeout=10)
    assert msg == {
        "command": "search_violation",
        "count": 1,
        "time": "2022-02-05T00:00:00+00:00",
    }
    for proto in (host, guest1, guest2):
        with pytest.raises(asyncio.TimeoutError):
            await read_until_command(proto, "search_violation", timeout=10)


@fast_forward(360)
async def test_violation_established_peer_multiple(mocker, lobby_server):
    mocker.patch(
        "server.ladder_service.violation_service.datetime_now",
        return_value=datetime(2022, 2, 5, tzinfo=timezone.utc)
    )
    protos, ids = await queue_players_for_matchmaking_2v2(lobby_server)
    host, guest1, guest2, guest3 = protos
    host_id, guest1_id, guest2_id, guest3_id = ids

    # Connect all players to the host
    await asyncio.gather(*[
        client_response(proto, timeout=60)
        for proto in protos
    ])
    await send_player_options(
        host,
        [host_id, "Color", 1],
        [guest1_id, "Color", 2],
        [guest2_id, "Color", 3],
        [guest3_id, "Color", 4],
    )

    # Set up connection matrix
    for id in (guest1_id, guest2_id, guest3_id):
        await host.send_message({
            "target": "game",
            "command": "EstablishedPeer",
            "args": [id],
        })
    # Guests only connect to the host
    await guest1.send_message({
        "target": "game",
        "command": "EstablishedPeer",
        "args": [host_id],
    })
    await guest2.send_message({
        "target": "game",
        "command": "EstablishedPeer",
        "args": [host_id],
    })
    await guest3.send_message({
        "target": "game",
        "command": "EstablishedPeer",
        "args": [host_id],
    })

    await read_until_command(host, "match_cancelled", timeout=120)
    for proto in (guest1, guest2, guest3):
        msg = await read_until_command(proto, "search_violation", timeout=10)
        assert msg == {
            "command": "search_violation",
            "count": 1,
            "time": "2022-02-05T00:00:00+00:00",
        }
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(host, "search_violation", timeout=10)


@fast_forward(360)
async def test_violation_persisted_across_logins(mocker, lobby_server):
    mocker.patch(
        "server.ladder_service.violation_service.datetime_now",
        return_value=datetime(2022, 2, 5, tzinfo=timezone.utc)
    )
    host_id, host, _, guest = await queue_players_for_matchmaking(lobby_server)

    await read_until_command(host, "match_cancelled", timeout=120)
    await read_until_command(guest, "match_cancelled", timeout=10)
    await read_until_command(host, "game_info", timeout=10, state="closed")

    # DEPRECATED: Because the game sends a game_launch to the guest after the
    # host times out, we need to simulate opening and closing the game before
    # we can queue again. If we wait for the timeout, our violations expire.
    await open_fa(guest)
    await guest.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Ended"]
    })

    # Second time searching there is no ban
    await start_search(host)
    await start_search(guest)
    await read_until_command(host, "match_cancelled", timeout=120)
    await read_until_command(guest, "match_cancelled", timeout=10)
    await read_until_command(host, "game_info", timeout=10, state="closed")

    # Third time searching there is a short ban
    await host.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": "ladder1v1"
    })

    msg = await read_until_command(host, "search_timeout", timeout=10)
    assert msg == {
        "command": "search_timeout",
        "timeouts": [{
            "player": host_id,
            "expires_at": "2022-02-05T00:10:00+00:00"
        }]
    }

    await host.close()

    _, _, host = await connect_and_sign_in(
        ("ladder1", "ladder1"),
        lobby_server
    )

    # Player should still be banned after re-logging
    await host.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": "ladder1v1"
    })

    msg = await read_until_command(host, "search_timeout", timeout=10)
    assert msg == {
        "command": "search_timeout",
        "timeouts": [{
            "player": host_id,
            "expires_at": "2022-02-05T00:10:00+00:00"
        }]
    }


@fast_forward(360)
async def test_violation_persisted_across_parties(mocker, lobby_server):
    mocker.patch(
        "server.ladder_service.violation_service.datetime_now",
        return_value=datetime(2022, 2, 5, tzinfo=timezone.utc)
    )
    host_id, host, guest_id, guest = await queue_players_for_matchmaking(lobby_server)

    await read_until_command(host, "match_cancelled", timeout=120)
    await read_until_command(guest, "match_cancelled", timeout=10)
    await read_until_command(host, "game_info", timeout=10, state="closed")

    # DEPRECATED: Because the game sends a game_launch to the guest after the
    # host times out, we need to simulate opening and closing the game before
    # we can queue again. If we wait for the timeout, our violations expire.
    await open_fa(guest)
    await guest.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Ended"]
    })

    # Second time searching there is no ban
    await start_search(host)
    await start_search(guest)
    await read_until_command(host, "match_cancelled", timeout=120)
    await read_until_command(guest, "match_cancelled", timeout=10)
    await read_until_command(host, "game_info", timeout=10, state="closed")

    # DEPRECATED: Because the game sends a game_launch to the guest after the
    # host times out, we need to simulate opening and closing the game before
    # we can queue again. If we wait for the timeout, our violations expire.
    await open_fa(guest)
    await guest.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Ended"]
    })

    # Third time searching there is a short ban
    await host.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": "ladder1v1"
    })

    msg = await read_until_command(host, "search_timeout", timeout=10)
    assert msg == {
        "command": "search_timeout",
        "timeouts": [{
            "player": host_id,
            "expires_at": "2022-02-05T00:10:00+00:00"
        }]
    }

    await invite_to_party(guest, host_id)
    await read_until_command(host, "party_invite", timeout=10)
    await accept_party_invite(host, guest_id)
    await read_until_command(guest, "update_party", timeout=10)

    # Guest should not be able to queue when player in their party has a ban
    await guest.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": "tmm2v2"
    })

    msg = await read_until_command(host, "search_timeout", timeout=10)
    assert msg == {
        "command": "search_timeout",
        "timeouts": [{
            "player": host_id,
            "expires_at": "2022-02-05T00:10:00+00:00"
        }]
    }
