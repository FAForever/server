import pytest

from server import ServerInstance
from server.config import config
from tests.utils import fast_forward

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
@fast_forward(100)
async def test_multiple_contexts(
    database,
    broadcast_service,
    game_service,
    player_service,
    geoip_service,
    ladder_service,
    tmp_user,
    policy_server,
    party_service,
    rating_service,
    oauth_service,
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
            "broadcast_service": broadcast_service,
            "game_service": game_service,
            "player_service": player_service,
            "geo_ip_service": geoip_service,
            "ladder_service": ladder_service,
            "rating_service": rating_service,
            "party_service": party_service,
            "oauth_service": oauth_service
        }
    )
    broadcast_service.server = instance

    await instance.listen(("127.0.0.1", 8111))
    await instance.listen(("127.0.0.1", 8112))

    ctx_1, ctx_2 = tuple(instance.contexts)

    # Connect one client to each context
    _, _, proto1 = await connect_and_sign_in(
        await tmp_user("User"), ctx_1
    )

    _, _, proto2 = await connect_and_sign_in(
        await tmp_user("User"), ctx_2
    )

    # Verify that the users can see each other
    await read_until(proto1, lambda m: has_player(m, "User1"), timeout=5)
    await read_until(proto2, lambda m: has_player(m, "User2"), timeout=5)

    # Host a game
    game_id = await host_game(proto1)
    msg = await read_until(
        proto2,
        lambda msg: msg["command"] == "game_info" and "games" not in msg,
        timeout=5
    )
    assert msg["uid"] == game_id

    await instance.shutdown()
    await proto1.close()
    await proto2.close()
