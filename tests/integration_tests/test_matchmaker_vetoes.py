from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command
from .test_game import queue_player_for_matchmaking, client_response, end_game_as_draw, gen_vetoes


async def test_vetoes_are_assigned_to_player_with_adjusting(lobby_server, player_service):
    async def test_vetoes(proto, vetoes, expected_vetoes):
        await proto.send_message({
            "command": "set_player_vetoes",
            "vetoes": vetoes
        })
        msg = await read_until_command(proto, "vetoes_info")
        assert msg['vetoes'] == expected_vetoes
        assert player_service.get_player(player_id).vetoes.to_dict()['vetoes'] == expected_vetoes

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

    for i in range(20):
        _, proto1 = await queue_player_for_matchmaking(
            ("ladder1", "ladder1"), lobby_server, "ladder1v1", gen_vetoes([(1, 1, 1)])
        )
        _, proto2 = await queue_player_for_matchmaking(
            ("ladder2", "ladder2"), lobby_server, "ladder1v1", gen_vetoes([(1, 2, 1)])
        )

        await read_until_command(proto1, "match_found", timeout=10)
        await read_until_command(proto2, "match_found", timeout=10)

        msg1 = await client_response(proto1)

        chosen_map_pool_version_id = msg1["map_pool_map_version_id"]
        assert chosen_map_pool_version_id == 3

        await end_game_as_draw([proto1, proto2], msg1["uid"])


@fast_forward(60)
async def test_dynamic_max_tokens_per_map(lobby_server, mocker):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 0.02)
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MIN", 0.01)

    for i in range(20):
        _, proto1 = await queue_player_for_matchmaking(
            ("ladder801", "ladder801"), lobby_server, "ladder1v1", gen_vetoes([(2, 4, 1), (2, 5, 1)])
        )
        _, proto2 = await queue_player_for_matchmaking(
            ("ladder802", "ladder802"), lobby_server, "ladder1v1", gen_vetoes([(2, 6, 1), (2, 7, 1)])
        )

        await read_until_command(proto1, "match_found", timeout=10)
        await read_until_command(proto2, "match_found", timeout=10)

        msg1 = await client_response(proto1)

        chosen_map_pool_version_id = msg1["map_pool_map_version_id"]
        assert chosen_map_pool_version_id == 8
        await end_game_as_draw([proto1, proto2], msg1["uid"])


@fast_forward(60)
async def test_partial_vetoes(lobby_server, mocker):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 0.02)
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MIN", 0.01)
    chosen_maps = set()

    for i in range(20):
        _, proto1 = await queue_player_for_matchmaking(
            ("ladder1001", "ladder1001"), lobby_server, "ladder1v1", gen_vetoes([(3, 9, 1), (3, 11, 1)])
        )
        _, proto2 = await queue_player_for_matchmaking(
            ("ladder1002", "ladder1002"), lobby_server, "ladder1v1", gen_vetoes([(3, 9, 1), (3, 10, 1)])
        )

        await read_until_command(proto1, "match_found", timeout=10)
        await read_until_command(proto2, "match_found", timeout=10)

        msg1 = await client_response(proto1)

        chosen_map_pool_version_id = msg1["map_pool_map_version_id"]
        chosen_maps.add(chosen_map_pool_version_id)
        assert chosen_map_pool_version_id in [10, 11], f"Expected map 10 or 11, got {chosen_map_pool_version_id}"
        await end_game_as_draw([proto1, proto2], msg1["uid"])

    assert chosen_maps == {10, 11}, f"Expected games on both maps 10 and 11, got {chosen_maps}"


@fast_forward(120)
async def test_vetoes_tmm(lobby_server, mocker):
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MAX", 0.02)
    mocker.patch("server.matchmaker.pop_timer.config.QUEUE_POP_TIME_MIN", 0.01)
    for i in range(20):
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
        chosen_map_pool_version_id = msg1["map_pool_map_version_id"]
        assert chosen_map_pool_version_id == 10
        await end_game_as_draw(players, msg1["uid"])
