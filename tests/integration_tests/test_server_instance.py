import asyncio

import pytest
from asynctest import exhaust_callbacks

from server import ServerInstance
from server.config import config
from server.protocol import QDataStreamProtocol, SimpleJsonProtocol

from .conftest import connect_and_sign_in, read_until
from .test_game import host_game


def has_player(msg, name):
    if msg["command"] != "player_info":
        return False

    for player in msg["players"]:
        if player["login"] == name:
            return True

    return False


@pytest.mark.asyncio
async def test_multiple_contexts(
    database,
    game_service,
    player_service,
    geoip_service,
    ladder_service,
    tmp_user,
    policy_server,
    party_service,
    event_loop
):
    config.USE_POLICY_SERVER = False

    instance = ServerInstance(
        "TestMultiContext",
        database,
        api_accessor=None,
        twilio_nts=None,
        loop=event_loop,
        _override_services={
            "game_service": game_service,
            "player_service": player_service,
            "geo_ip_service": geoip_service,
            "ladder_service": ladder_service,
            "party_service": party_service,
        }
    )
    await instance.listen(("127.0.0.1", 8111), QDataStreamProtocol)
    await instance.listen(("127.0.0.1", 8112), SimpleJsonProtocol)

    ctx_1, ctx_2 = tuple(instance.contexts)
    if ctx_1.protocol_class is SimpleJsonProtocol:
        ctx_1, ctx_2 = ctx_2, ctx_1

    # Connect one client to each context
    _, _, proto1 = await connect_and_sign_in(
        await tmp_user("QDataStreamUser"),
        ctx_1,
        QDataStreamProtocol
    )

    _, _, proto2 = await connect_and_sign_in(
        await tmp_user("SimpleJsonUser"),
        ctx_2,
        SimpleJsonProtocol
    )

    # Verify that the users can see each other
    await asyncio.wait_for(
        read_until(proto1, lambda m: has_player(m, "SimpleJsonUser1")),
        timeout=5
    )
    await asyncio.wait_for(
        read_until(proto2, lambda m: has_player(m, "QDataStreamUser1")),
        timeout=5
    )

    # Host a game
    game_id = await host_game(proto1)
    msg = await read_until(
        proto2,
        lambda msg: msg["command"] == "game_info" and "games" not in msg
    )
    assert msg["uid"] == game_id

    await instance.shutdown()
    await exhaust_callbacks(event_loop)
