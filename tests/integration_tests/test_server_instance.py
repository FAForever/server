import asyncio

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
    veto_service,
):
    """
    Verify multiple ServerContexts share state on one ServerInstance.

    A single ServerInstance can host more than one ServerContext listening on
    different ports; both must accept connections and broadcast shared state.
    """
    config.USE_POLICY_SERVER = False

    loop = asyncio.get_running_loop()
    instance = ServerInstance(
        "TestMultiContext",
        database,
        loop=loop,
        _override_services={
            "broadcast_service": broadcast_service,
            "game_service": game_service,
            "player_service": player_service,
            "geo_ip_service": geoip_service,
            "ladder_service": ladder_service,
            "rating_service": rating_service,
            "party_service": party_service,
            "oauth_service": oauth_service,
            "veto_service": veto_service,
        }
    )
    broadcast_service.server = instance

    await instance.listen(("127.0.0.1", 0), name="ws-a")
    await instance.listen(("127.0.0.1", 0), name="ws-b")

    ctx_1, ctx_2 = tuple(instance.contexts)

    _, _, proto1 = await connect_and_sign_in(
        await tmp_user("UserA"), ctx_1
    )

    _, _, proto2 = await connect_and_sign_in(
        await tmp_user("UserB"), ctx_2
    )

    await read_until(
        proto1,
        lambda m: has_player(m, "UserB1"),
        timeout=5
    )
    await read_until(
        proto2,
        lambda m: has_player(m, "UserA1"),
        timeout=5
    )

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
