from server.players import PlayerState
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command
from .test_game import (
    client_response,
    end_game_as_draw,
    gen_vetoes,
    queue_player_for_matchmaking
)


async def test_used_pools_have_some_maps_and_all_map_names_are_unique(ladder_service):
    used_map_pools = {}
    for queue in ladder_service.queues.values():
        for mq_map_pool in queue.map_pools.values():
            pool_id = mq_map_pool.map_pool.id
            if pool_id in [1, 2, 3]:
                used_map_pools[pool_id] = mq_map_pool

    assert len(used_map_pools) == 3

    for mq_map_pool in used_map_pools.values():
        maps = list(mq_map_pool.map_pool.maps.values())
        folder_names = [m.folder_name for m in maps if hasattr(m, "folder_name")]
        assert len(folder_names) > 0, f"Pool {mq_map_pool.map_pool.id} has no regular maps"
        assert len(folder_names) == len(set(folder_names)), f"Pool {mq_map_pool.map_pool.id} has duplicate map names: {folder_names}"


async def test_vetoes_are_assigned_to_player_with_adjusting(lobby_server, player_service):
    async def test_vetoes(proto, vetoes, expected_vetoes):
        await proto.send_message({
            "command": "set_player_vetoes",
            "vetoes": vetoes
        })
        if vetoes != expected_vetoes:
            msg = await read_until_command(proto, "vetoes_info")
            assert msg["vetoes"] == expected_vetoes
        else:
            # modern problems require modern solutions
            await proto.send_message({"command": "ping"})
            await read_until_command(proto, "pong")
        assert player_service.get_player(player_id).vetoes.to_dict()["vetoes"] == expected_vetoes

    player_id, _, proto = await connect_and_sign_in(("test", "test_password"), lobby_server)
    await read_until_command(proto, "game_info")
    await test_vetoes(proto, gen_vetoes([(1, 1, 1)]), gen_vetoes([(1, 1, 1)]))
    await test_vetoes(proto, gen_vetoes([(1, 1, 2)]), gen_vetoes([(1, 1, 1)]))
    await test_vetoes(proto, gen_vetoes([(1, 2, 1)]), gen_vetoes([(1, 2, 1)]))
    await test_vetoes(proto, gen_vetoes([(1, 1, 0)]), gen_vetoes([]))


@fast_forward(60)
async def test_if_veto_bans_working(lobby_server, mocker):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 0.02)
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MIN", 0.01)

    for _ in range(20):
        _, proto1 = await queue_player_for_matchmaking(
            ("ladder1", "ladder1"), lobby_server, "ladder1v1", gen_vetoes([(1, 1, 1)])
        )
        _, proto2 = await queue_player_for_matchmaking(
            ("ladder2", "ladder2"), lobby_server, "ladder1v1", gen_vetoes([(1, 2, 1)])
        )

        await read_until_command(proto1, "match_found", timeout=10)
        await read_until_command(proto2, "match_found", timeout=10)

        msg1 = await client_response(proto1)

        assert msg1["mapname"] == "scmp_015.v0003"

        await end_game_as_draw([proto1, proto2], msg1["uid"])


@fast_forward(60)
async def test_dynamic_max_tokens_per_map(lobby_server, mocker):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 0.02)
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MIN", 0.01)

    for _ in range(20):
        _, proto1 = await queue_player_for_matchmaking(
            ("ladder801", "ladder801"), lobby_server, "ladder1v1", gen_vetoes([(2, 4, 1), (2, 5, 1)])
        )
        _, proto2 = await queue_player_for_matchmaking(
            ("ladder802", "ladder802"), lobby_server, "ladder1v1", gen_vetoes([(2, 6, 1), (2, 7, 1)])
        )

        await read_until_command(proto1, "match_found", timeout=10)
        await read_until_command(proto2, "match_found", timeout=10)

        msg1 = await client_response(proto1)

        assert msg1["mapname"] == "scmp_015.v0003"
        await end_game_as_draw([proto1, proto2], msg1["uid"])


@fast_forward(60)
async def test_partial_vetoes(lobby_server, mocker):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 0.02)
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MIN", 0.01)
    chosen_maps = set()

    for _ in range(20):
        _, proto1 = await queue_player_for_matchmaking(
            ("ladder1001", "ladder1001"), lobby_server, "ladder1v1", gen_vetoes([(3, 9, 1), (3, 11, 1)])
        )
        _, proto2 = await queue_player_for_matchmaking(
            ("ladder1002", "ladder1002"), lobby_server, "ladder1v1", gen_vetoes([(3, 9, 1), (3, 10, 1)])
        )

        await read_until_command(proto1, "match_found", timeout=10)
        await read_until_command(proto2, "match_found", timeout=10)

        msg1 = await client_response(proto1)

        chosen_mapname = msg1["mapname"]
        chosen_maps.add(chosen_mapname)
        assert chosen_mapname in ["scmp_002", "scmp_003"], f"Expected scmp_002 or scmp_003, got {chosen_mapname}"
        await end_game_as_draw([proto1, proto2], msg1["uid"])

    assert chosen_maps == {"scmp_002", "scmp_003"}, f"Expected games on both scmp_002 and scmp_003, got {chosen_maps}"


@fast_forward(120)
async def test_vetoes_tmm(lobby_server, mocker):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 0.02)
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MIN", 0.01)
    for _ in range(20):
        player_vetoes = [
            ("ladder1", gen_vetoes([(4, 9, 1)])),
            ("ladder2", gen_vetoes([(4, 9, 1)])),
            ("ladder3", gen_vetoes([(4, 11, 1)])),
            ("ladder4", gen_vetoes([(4, 11, 1)])),
        ]

        players = []
        for username, vetoes in player_vetoes:
            _, proto = await queue_player_for_matchmaking(
                (username, username), lobby_server, "tmm2v2", vetoes
            )
            players.append(proto)

        for proto in players:
            await read_until_command(proto, "match_found", timeout=30)

        msg1 = await client_response(players[0])
        assert msg1["mapname"] == "scmp_002"
        await end_game_as_draw(players, msg1["uid"])


@fast_forward(120)
async def test_pool_config_changes_causing_forced_update_and_stops_search(player_service, lobby_server, database, ladder_service):
    player_id, proto = await queue_player_for_matchmaking(
        ("test", "test_password"), lobby_server, "ladder1v1", gen_vetoes([(1, 1, 1)])
    )
    player = player_service.get_player(player_id)
    assert player.state == PlayerState.SEARCHING_LADDER
    try:
        async with database.acquire() as conn:
            await conn.execute(
                "UPDATE matchmaker_queue_map_pool SET veto_tokens_per_player = 0 WHERE id = 1"
            )
        await ladder_service.update_data()
        msg = await read_until_command(proto, "vetoes_info", timeout=10)
        assert msg.get("forced") is True
        assert msg["vetoes"] == gen_vetoes([])
        assert player.vetoes.to_dict()["vetoes"] == gen_vetoes([])
        assert player.state == PlayerState.IDLE
    finally:
        async with database.acquire() as conn:
            await conn.execute(
                "UPDATE matchmaker_queue_map_pool SET veto_tokens_per_player = 1 WHERE id = 1"
            )


@fast_forward(120)
async def test_map_pool_changes_causing_silent_update_and_not_stops_search(player_service, lobby_server, database, ladder_service):
    player_id, proto = await queue_player_for_matchmaking(
        ("test", "test_password"), lobby_server, "ladder1v1", gen_vetoes([(1, 1, 1)])
    )
    player = player_service.get_player(player_id)
    assert player.state == PlayerState.SEARCHING_LADDER

    try:
        async with database.acquire() as conn:
            await conn.execute(
                "DELETE FROM map_pool_map_version WHERE id = 1"
            )
        await ladder_service.update_data()
        msg = await read_until_command(proto, "vetoes_info", timeout=10)

        assert msg.get("forced") is False
        assert msg["vetoes"] == gen_vetoes([])
        assert player.state == PlayerState.SEARCHING_LADDER
    finally:
        async with database.acquire() as conn:
            await conn.execute(
                "REPLACE INTO map_pool_map_version (id, map_pool_id, map_version_id, weight, map_params) VALUES (1, 1, 15, 1, NULL)"
            )
