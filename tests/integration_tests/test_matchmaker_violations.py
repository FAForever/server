import asyncio
from datetime import datetime, timezone

from tests.utils import fast_forward

from .conftest import read_until_command
from .test_game import open_fa, queue_players_for_matchmaking, start_search


@fast_forward(360)
async def test_violation_for_guest_timeout(mocker, lobby_server):
    mock_now = mocker.patch(
        "server.ladder_service.violation_service.datetime_now",
        return_value=datetime(2022, 2, 5, tzinfo=timezone.utc)
    )
    _, host, guest_id, guest = await queue_players_for_matchmaking(lobby_server)

    # The player that queued last will be the host
    async def launch_game_and_timeout_guest():
        await read_until_command(host, "game_launch")
        await open_fa(host)
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
