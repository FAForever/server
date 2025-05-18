
from tests.utils import fast_forward

from .conftest import connect_and_sign_in, read_until_command


@fast_forward(60)
async def test_vetos(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await read_until_command(proto, "game_info")

    await proto.send_message({
        "command": "set_player_vetoes",
        "vetoes": [
            {
                # ladder1v1
                "matchmaker_queue_map_pool_id": 1,
                "map_pool_map_version_id": 1,
                "veto_tokens_applied": 2,
            },
            {
                # ladder1v1
                "matchmaker_queue_map_pool_id": 1,
                "map_pool_map_version_id": 2,
                "veto_tokens_applied": 2,
            },
            {
                # ladder1v1
                "matchmaker_queue_map_pool_id": 2,
                "map_pool_map_version_id": 4,
                "veto_tokens_applied": 2,
            },
            {
                # ladder1v1
                "matchmaker_queue_map_pool_id": 2,
                "map_pool_map_version_id": 5,
                "veto_tokens_applied": 2,
            },
            {
                # gameoptions
                "matchmaker_queue_map_pool_id": 6,
                "map_pool_map_version_id": 1,
                # Different vetoes for the same maps in a different pool
                "veto_tokens_applied": 3,
            },
            {
                # gameoptions
                "matchmaker_queue_map_pool_id": 6,
                "map_pool_map_version_id": 2,
                # Different vetoes for the same maps in a different pool
                "veto_tokens_applied": 3,
            }
        ],
    })

    msg = await read_until_command(proto, "vetoes_info", timeout=10)

    # TODO: Implement veto config in test data
    assert msg == {
        "command": "vetoes_info",
        "vetoes": [],
    }
