import asyncio
import gc
from collections import defaultdict

import pytest
from sqlalchemy import select

from server.db.models import game_player_stats
from server.games.game_results import GameOutcome
from server.protocol import Protocol
from tests.utils import fast_forward

from .conftest import (
    connect_and_sign_in,
    connect_mq_consumer,
    read_until,
    read_until_command
)

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def host_game(
    proto: Protocol,
    *,
    mod: str = "faf",
    visibility: str = "public",
    **kwargs
) -> int:
    await proto.send_message({
        "command": "game_host",
        "mod": mod,
        "visibility": visibility,
        **kwargs
    })
    msg = await read_until_command(proto, "game_launch")
    game_id = int(msg["uid"])

    await open_fa(proto)

    return game_id


async def join_game(proto: Protocol, uid: int):
    await proto.send_message({
        "command": "game_join",
        "uid": uid
    })
    await read_until_command(proto, "game_launch", timeout=10)
    await open_fa(proto)
    # HACK: Yield long enough for the server to process our message
    await asyncio.sleep(0.5)


async def client_response(proto):
    msg = await read_until_command(proto, "game_launch", timeout=10)
    await open_fa(proto)
    return msg


async def open_fa(proto):
    """Simulate FA opening"""

    await proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Idle"]
    })
    await proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Lobby"]
    })


async def queue_player_for_matchmaking(user, lobby_server, queue_name):
    _, _, proto = await connect_and_sign_in(user, lobby_server)
    await read_until_command(proto, "game_info")
    await proto.send_message({
        "command": "set_party_factions",
        "factions": ["uef"]
    })
    await proto.send_message({
        "command": "game_matchmaking",
        "state": "start",
        "queue_name": queue_name
    })
    await read_until_command(
        proto,
        "search_info",
        state="start",
        queue_name=queue_name,
        timeout=10
    )

    return proto


async def queue_players_for_matchmaking(
    lobby_server,
    queue_name: str = "ladder1v1"
):
    proto1 = await queue_player_for_matchmaking(
        ("ladder1", "ladder1"),
        lobby_server,
        queue_name
    )
    proto2 = await queue_player_for_matchmaking(
        ("ladder2", "ladder2"),
        lobby_server,
        queue_name
    )

    # If the players did not match, this will fail due to a timeout error
    await read_until_command(proto1, "match_found", timeout=30)
    await read_until_command(proto2, "match_found")

    return proto1, proto2


async def queue_temp_players_for_matchmaking(
    lobby_server,
    tmp_user,
    num_players,
    queue_name,
):
    """
    Queue an arbitrary number of players for matchmaking in a particular queue
    by setting up temp users.
    """
    users = await asyncio.gather(*[
        tmp_user(queue_name)
        for _ in range(num_players)
    ])
    protos = await asyncio.gather(*[
        queue_player_for_matchmaking(user, lobby_server, queue_name)
        for user in users
    ])

    # If the players did not match, this will fail due to a timeout error
    await asyncio.gather(*[
        read_until_command(proto, "match_found", timeout=30)
        for proto in protos
    ])

    return protos


async def get_player_ratings(proto, *names, rating_type="global"):
    """
    Wait for `player_info` messages until all player names have been found.
    Then return a dictionary containing all those players ratings
    """
    ratings = {}
    while set(ratings.keys()) != set(names):
        msg = await read_until_command(proto, "player_info")
        ratings.update({
            player_info["login"]: player_info["ratings"][rating_type]["rating"]
            for player_info in msg["players"]
        })
    return ratings


async def get_player_ratings_all(proto, *names, old_ratings={}):
    """
    Like `get_player_ratings` but find all rating types instead of just one and
    return a nested dictionary containing all those ratings.

    If old_ratings is passed, wait for ratings to be different from old_ratings.
    """
    def _nested_keys(nested_dict):
        return set(k + r for k, v in nested_dict.items() for r in v.keys())

    ratings = defaultdict(dict)
    target_keys = _nested_keys(old_ratings)
    while _nested_keys(ratings) != target_keys:
        msg = await read_until_command(proto, "player_info")
        for player_info in msg["players"]:
            for rating_type, rating in player_info["ratings"].items():
                login = player_info["login"]
                player_rating = tuple(rating["rating"])
                if player_rating != old_ratings.get(login, {}).get(rating_type):
                    ratings[login][rating_type] = player_rating

    return dict(ratings)


async def send_player_options(proto, *options):
    for option in options:
        await proto.send_message({
            "target": "game",
            "command": "PlayerOption",
            "args": list(option)
        })


@fast_forward(60)
async def test_game_ended_rates_game(lobby_server):
    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")
    ratings = await get_player_ratings(host_proto, "test", "Rhiza")

    # Set up the game
    game_id = await host_game(host_proto)
    await join_game(guest_proto, game_id)
    # Set player options
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "Team", 1],
        [host_id, "StartSpot", 0],
        [host_id, "Faction", 1],
        [host_id, "Color", 1],
        [guest_id, "Army", 2],
        [guest_id, "Team", 1],
        [guest_id, "StartSpot", 1],
        [guest_id, "Faction", 1],
        [guest_id, "Color", 2],
    )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    await read_until(
        host_proto,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Reports results
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [1, "victory 10"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [2, "defeat -10"]
        })
    # Report GameEnded
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })

    # Check that the ratings were updated
    new_ratings = await get_player_ratings(host_proto, "test", "Rhiza")

    assert ratings["test"][0] < new_ratings["test"][0]
    assert ratings["Rhiza"][0] > new_ratings["Rhiza"][0]

    # Now disconnect both players
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    # The game should only be rated once
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(host_proto, "player_info", timeout=10)


@pytest.mark.rabbitmq
@fast_forward(30)
async def test_game_ended_broadcasts_rating_update(lobby_server, channel):
    mq_proto_all = await connect_mq_consumer(
        lobby_server,
        channel,
        "success.rating.update"
    )
    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")
    old_ratings = await get_player_ratings(host_proto, "test", "Rhiza")

    # Set up the game
    game_id = await host_game(host_proto)
    await join_game(guest_proto, game_id)
    # Set player options
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "Team", 1],
        [host_id, "StartSpot", 0],
        [host_id, "Faction", 1],
        [host_id, "Color", 1],
        [guest_id, "Army", 2],
        [guest_id, "Team", 1],
        [guest_id, "StartSpot", 1],
        [guest_id, "Faction", 1],
        [guest_id, "Color", 2],
    )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    await read_until(
        host_proto,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Reports results
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [1, "victory 10"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [2, "defeat -10"]
        })
    # Report GameEnded
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })

    new_persisted_ratings = await get_player_ratings(host_proto, "test", "Rhiza")

    rhiza_message = {
        "player_id": 3,  # Rhiza
        "rating_type": "global",
        "new_rating_mean": new_persisted_ratings["Rhiza"][0],
        "new_rating_deviation": new_persisted_ratings["Rhiza"][1],
        "old_rating_mean": old_ratings["Rhiza"][0],
        "old_rating_deviation": old_ratings["Rhiza"][1],
        "outcome": "DEFEAT"
    }

    test_message = {
        "player_id": 1,  # test
        "rating_type": "global",
        "new_rating_mean": new_persisted_ratings["test"][0],
        "new_rating_deviation": new_persisted_ratings["test"][1],
        "old_rating_mean": old_ratings["test"][0],
        "old_rating_deviation": old_ratings["test"][1],
        "outcome": "VICTORY"
    }

    expected_messages_by_id = {
        message["player_id"]: message
        for message in [rhiza_message, test_message]
    }

    first_message = await asyncio.wait_for(mq_proto_all.read_message(), timeout=5)
    second_message = await asyncio.wait_for(mq_proto_all.read_message(), timeout=5)

    first_id = first_message["player_id"]
    expected_message = expected_messages_by_id[first_id]
    assert first_message == pytest.approx(expected_message)

    second_id = second_message["player_id"]
    assert second_id != first_id
    expected_message = expected_messages_by_id[second_id]
    assert second_message == pytest.approx(expected_message)

    # Now disconnect both players
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    # There should be no further updates
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(mq_proto_all.read_message(), timeout=10)


@fast_forward(100)
async def test_game_with_foed_player(lobby_server):
    _, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    _, _, guest_proto = await connect_and_sign_in(
        ("foed_by_test", "foe"), lobby_server
    )

    # Set up the game
    game_id = await host_game(host_proto)
    with pytest.raises(asyncio.TimeoutError):
        await join_game(guest_proto, game_id)


@fast_forward(100)
async def test_partial_game_ended_rates_game(lobby_server, tmp_user):
    """
    Test that game is rated as soon as all players have either disconnected
    or sent `GameEnded`
    """
    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guests = []
    for _ in range(3):
        user = await tmp_user("Guest")
        guest_id, _, proto = await connect_and_sign_in(
            user, lobby_server
        )
        guests.append((guest_id, user[0], proto))

    await asyncio.gather(*(
        read_until_command(proto, "game_info")
        for (_, _, proto) in guests
    ))
    ratings = await get_player_ratings(
        host_proto,
        "test",
        *(name for _, name, _ in guests)
    )

    # Set up the game
    game_id = await host_game(host_proto)
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "StartSpot", 1],
        [host_id, "Color", 1],
        [host_id, "Faction", 1],
        [host_id, "Team", 2],
    )
    for i, (guest_id, _, guest_proto) in enumerate(guests):
        await join_game(guest_proto, game_id)
        # Set player options
        await send_player_options(
            host_proto,
            [guest_id, "Army", i+2],
            [guest_id, "StartSpot", i+2],
            [guest_id, "Color", i+2],
            [guest_id, "Faction", 1],
            [guest_id, "Team", 3 if i % 2 == 0 else 2]
        )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })
    await read_until(
        host_proto,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Reports results (lazy, just the host reports. This should still work)
    for result in (
        [1, "victory 10"],
        [2, "defeat -10"],
        [3, "victory 10"],
        [4, "defeat -10"]
    ):
        await host_proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": result
        })
    # Report GameEnded
    await host_proto.send_message({
        "target": "game",
        "command": "GameEnded",
        "args": []
    })
    # Guests disconnect without sending `GameEnded`
    for i, (_, _, guest_proto) in enumerate(guests):
        await guest_proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    # Check that the ratings were updated
    new_ratings = await get_player_ratings(
        host_proto,
        "test",
        *(name for _, name, _ in guests)
    )

    assert ratings["test"][0] < new_ratings["test"][0]
    assert ratings["Guest1"][0] > new_ratings["Guest1"][0]
    assert ratings["Guest2"][0] < new_ratings["Guest2"][0]
    assert ratings["Guest3"][0] > new_ratings["Guest3"][0]

    # Now disconnect the host too
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Ended"]
    })

    # The game should only be rated once
    with pytest.raises(asyncio.TimeoutError):
        await read_until_command(host_proto, "player_info", timeout=10)


@fast_forward(100)
async def test_ladder_game_draw_bug(lobby_server, database):
    """
    This simulates the infamous "draw bug" where a player could self destruct
    their own ACU in order to kill the enemy ACU and be awarded a victory
    instead of a draw.
    """
    proto1, proto2 = await queue_players_for_matchmaking(lobby_server)

    msg1, msg2 = await asyncio.gather(*[
        client_response(proto) for proto in (proto1, proto2)
    ])
    game_id = msg1["uid"]
    army1 = msg1["map_position"]
    army2 = msg2["map_position"]

    for proto in (proto1, proto2):
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Launching"]
        })
    await read_until(
        proto1,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )

    # Player 1 ctrl-k's
    for result in (
        [army1, "defeat -10"],
        [army1, "score 1"],
        [army2, "defeat -10"]
    ):
        for proto in (proto1, proto2):
            await proto.send_message({
                "target": "game",
                "command": "GameResult",
                "args": result
            })

    for proto in (proto1, proto2):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })

    ratings = await get_player_ratings_all(
        proto1,
        "ladder1",
        "ladder2",
        old_ratings={
            "ladder1": {
                "global": (1500, 500),
                "ladder_1v1": (1500, 500),
            },
            "ladder2": {
                "global": (1500, 500),
                "ladder_1v1": (1500, 500),
            },
        }
    )

    # Both start at (1500, 500).
    # When rated as a draw the means should barely change.
    assert 0 < abs(ratings["ladder1"]["ladder_1v1"][0] - 1500.) < 1
    assert 0 < abs(ratings["ladder2"]["ladder_1v1"][0] - 1500.) < 1

    # Global rating should also be updated
    assert 0 < abs(ratings["ladder1"]["global"][0] - 1500.) < 1
    assert 0 < abs(ratings["ladder2"]["global"][0] - 1500.) < 1

    async with database.acquire() as conn:
        result = await conn.execute(
            select([game_player_stats]).where(
                game_player_stats.c.gameId == game_id
            )
        )
        for row in result:
            assert row.result == GameOutcome.DEFEAT
            assert row.score == 0


@fast_forward(15)
async def test_ladder_game_not_joinable(lobby_server):
    """
    We should not be able to join AUTO_LOBBY games using the `game_join` command.
    """
    _, _, test_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    proto1, proto2 = await queue_players_for_matchmaking(lobby_server)
    await read_until_command(test_proto, "game_info")

    msg = await read_until_command(proto1, "game_launch")
    await open_fa(proto1)

    game_uid = msg["uid"]

    await test_proto.send_message({
        "command": "game_join",
        "uid": game_uid
    })

    msg = await read_until_command(test_proto, "notice", timeout=5)
    assert msg == {
        "command": "notice",
        "style": "error",
        "text": "The game cannot be joined in this way."
    }


@pytest.mark.flaky
@fast_forward(60)
async def test_gamestate_ended_clears_references(
    lobby_server,
    game_service,
    player_service
):
    test_id, _, test_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, rhiza_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(test_proto, "game_info")
    await read_until_command(rhiza_proto, "game_info")

    # Set up the game
    game_id = await host_game(test_proto)
    await join_game(rhiza_proto, game_id)
    # Set player options
    await send_player_options(
        test_proto,
        [test_id, "Army", 1],
        [test_id, "Team", 1],
        [test_id, "StartSpot", 1],
        [test_id, "Faction", 1],
        [test_id, "Color", 1],
        [rhiza_id, "Army", 2],
        [rhiza_id, "Team", 1],
        [rhiza_id, "StartSpot", 2],
        [rhiza_id, "Faction", 1],
        [rhiza_id, "Color", 1],
    )

    # Launch game
    await test_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })
    await asyncio.sleep(0.1)

    game = game_service[game_id]

    assert len(game.connections) == 2

    test = player_service[test_id]
    rhiza = player_service[rhiza_id]

    # Player leaves and sends results after
    await rhiza_proto.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })
    await rhiza_proto.send_message({
        "command": "GameResult",
        "target": "game",
        "args": [1, "victory 10"]
    })
    await asyncio.sleep(0.1)
    gc.collect()
    assert rhiza.game_connection is None
    assert len(game.connections) == 1
    assert len(game._results) == 0

    # Player sends results first and then leaves
    await test_proto.send_message({
        "command": "GameResult",
        "target": "game",
        "args": [2, "victory 10"]
    })
    await test_proto.send_message({
        "command": "GameState",
        "target": "game",
        "args": ["Ended"]
    })

    await read_until_command(
        test_proto,
        "game_info",
        state="closed",
        num_players=0
    )
    await asyncio.sleep(0.1)
    gc.collect()
    assert test.game_connection is None
    assert len(game.connections) == 0
    assert len(game._results) == 1

    assert game_id not in game_service

    assert test.lobby_connection.game_connection is None
    assert rhiza.lobby_connection.game_connection is None


@fast_forward(30)
async def test_gamestate_ended_modifies_player_list(lobby_server):
    test_id, _, test_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    rhiza_id, _, rhiza_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(test_proto, "game_info")
    await read_until_command(rhiza_proto, "game_info")

    # Set up the game
    game_id = await host_game(test_proto)
    await join_game(rhiza_proto, game_id)
    # Set player options
    await send_player_options(
        test_proto,
        [test_id, "Army", 1],
        [test_id, "Team", 1],
        [test_id, "StartSpot", 1],
        [test_id, "Faction", 1],
        [test_id, "Color", 1],
        [rhiza_id, "Army", 2],
        [rhiza_id, "Team", 1],
        [rhiza_id, "StartSpot", 2],
        [rhiza_id, "Faction", 1],
        [rhiza_id, "Color", 1],
    )

    teams = {"1": ["test", "Rhiza"]}
    await read_until_command(test_proto, "game_info", teams=teams)
    await read_until_command(rhiza_proto, "game_info", teams=teams)

    # Launch game, trggers another game_info message
    await test_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    msg1 = await read_until_command(test_proto, "game_info")
    msg2 = await read_until_command(rhiza_proto, "game_info")
    assert msg1["teams"] == msg2["teams"] == {"1": ["test", "Rhiza"]}

    # One player leaves
    await test_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Ended"]
    })

    # game_info shows only the connected player
    msg1 = await read_until_command(test_proto, "game_info")
    msg2 = await read_until_command(rhiza_proto, "game_info")
    assert msg1["teams"] == msg2["teams"] == {"1": ["Rhiza"]}


@pytest.mark.rabbitmq
@fast_forward(30)
async def test_galactic_war_1v1_game_ended_broadcasts_army_results(
    lobby_server,
    channel
):
    mq_proto_all = await connect_mq_consumer(
        lobby_server,
        channel,
        "success.gameResults.create"
    )

    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")

    # Set up the game
    game_id = await host_game(host_proto, mod="gw")
    await join_game(guest_proto, game_id)
    # Set player options
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "Team", 1],
        [host_id, "StartSpot", 1],
        [host_id, "Faction", 1],
        [host_id, "Color", 1],
        [guest_id, "Army", 2],
        [guest_id, "Team", 2],
        [guest_id, "StartSpot", 2],
        [guest_id, "Faction", 2],
        [guest_id, "Color", 2],
    )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    await read_until(
        host_proto,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Report results
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [1, "victory 10"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [2, "recall defeat -5"]
        })
    # Report GameEnded
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })
    # Now disconnect both players
    for proto in (host_proto, guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    message = await asyncio.wait_for(mq_proto_all.read_message(), timeout=5)

    assert message == {
        "game_id": 41956,
        "rating_type": "global",
        "map_id": 7,
        "featured_mod": "gw",
        "sim_mod_ids": [],
        "commander_kills": {},
        "validity": "VALID",
        "teams": [
            {
                "outcome": "DEFEAT",
                "player_ids": [3],
                "army_results": [
                    {
                        "player_id": 3,
                        "army": 2,
                        "army_outcome": "DEFEAT",
                        "metadata": ["recall"],
                    },
                ]
            },
            {
                "outcome": "VICTORY",
                "player_ids": [1],
                "army_results": [
                    {
                        "player_id": 1,
                        "army": 1,
                        "army_outcome": "VICTORY",
                        "metadata": [],
                    },
                ]
            }
        ]
    }

    with pytest.raises(asyncio.TimeoutError):
        # We expect only one message to be broadcast
        await asyncio.wait_for(mq_proto_all.read_message(), timeout=5)


@pytest.mark.rabbitmq
@fast_forward(30)
async def test_galactic_war_2v1_game_ended_broadcasts_army_results(lobby_server, channel):
    mq_proto_all = await connect_mq_consumer(
        lobby_server,
        channel,
        "success.gameResults.create"
    )

    host_id, _, host_proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    guest_id, _, guest_proto = await connect_and_sign_in(
        ("Rhiza", "puff_the_magic_dragon"), lobby_server
    )
    other_guest_id, _, other_guest_proto = await connect_and_sign_in(
        ("newbie", "password"), lobby_server
    )
    await read_until_command(guest_proto, "game_info")
    await read_until_command(other_guest_proto, "game_info")

    # Set up the game
    game_id = await host_game(host_proto, mod="gw")
    await join_game(guest_proto, game_id)
    await join_game(other_guest_proto, game_id)
    # Set player options
    await send_player_options(
        host_proto,
        [host_id, "Army", 1],
        [host_id, "Team", 0],
        [host_id, "StartSpot", 1],
        [host_id, "Faction", 1],
        [host_id, "Color", 1],
        [guest_id, "Army", 2],
        [guest_id, "Team", 0],
        [guest_id, "StartSpot", 2],
        [guest_id, "Faction", 1],
        [guest_id, "Color", 2],
        [other_guest_id, "Army", 3],
        [other_guest_id, "Team", 2],
        [other_guest_id, "StartSpot", 3],
        [other_guest_id, "Faction", 2],
        [other_guest_id, "Color", 3],
    )

    # Launch game
    await host_proto.send_message({
        "target": "game",
        "command": "GameState",
        "args": ["Launching"]
    })

    await read_until(
        host_proto,
        lambda cmd: cmd["command"] == "game_info" and cmd["launched_at"]
    )
    await host_proto.send_message({
        "target": "game",
        "command": "EnforceRating",
        "args": []
    })

    # End the game
    # Report results
    for proto in (host_proto, guest_proto, other_guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [1, "victory 10"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [2, "recall victory 5"]
        })
        await proto.send_message({
            "target": "game",
            "command": "GameResult",
            "args": [3, "recall defeat -5"]
        })
    # Report GameEnded
    for proto in (host_proto, guest_proto, other_guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameEnded",
            "args": []
        })
    # Now disconnect all players
    for proto in (host_proto, guest_proto, other_guest_proto):
        await proto.send_message({
            "target": "game",
            "command": "GameState",
            "args": ["Ended"]
        })

    message = await asyncio.wait_for(mq_proto_all.read_message(), timeout=5)

    assert message == {
        "commander_kills": {},
        "featured_mod": "gw",
        "game_id": 41956,
        "map_id": 7,
        "rating_type": "global",
        "sim_mod_ids": [],
        "teams": [
            {
                "army_results": [
                    {
                        "player_id": 1,
                        "army": 1,
                        "army_outcome": "VICTORY",
                        "metadata": [],
                    },
                    {
                        "player_id": 3,
                        "army": 2,
                        "army_outcome": "VICTORY",
                        "metadata": ["recall"],
                    },
                ],
                "outcome": "UNKNOWN",
                "player_ids": [1, 3]
            },
            {
                "army_results": [
                    {
                        "player_id": 6,
                        "army": 3,
                        "army_outcome": "DEFEAT",
                        "metadata": ["recall"],
                    },
                ],
                "outcome": "UNKNOWN",
                "player_ids": [6]
            },
        ],
        "validity": "UNEVEN_TEAMS_NOT_RANKED",
    }

    with pytest.raises(asyncio.TimeoutError):
        # We expect only one message to be broadcast
        await asyncio.wait_for(mq_proto_all.read_message(), timeout=5)
