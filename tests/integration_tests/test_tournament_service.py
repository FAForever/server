import pytest

from server import TournamentService
from server.config import config
from server.message_queue_service import MessageQueueService
from tests.integration_tests.conftest import (
    connect_and_sign_in,
    read_until_command
)

pytestmark = pytest.mark.rabbitmq


async def test_create_game_by_message(message_queue_service: MessageQueueService,
                                      tournament_service: TournamentService, lobby_server):
    _, _, proto1 = await connect_and_sign_in(
        ("test", "test_password"), lobby_server
    )
    await message_queue_service.declare_exchange(config.MQ_EXCHANGE_NAME)
    await message_queue_service.publish(config.MQ_EXCHANGE_NAME, "request.match.create",
                                        {
                                            "request_id": "9124e8c9-c62f-43c3-bb64-94f3093f2997",
                                            "game_name": "My game name",
                                            "participants": [
                                                {
                                                    "team": 1,
                                                    "slot": 1,
                                                    "faction": 1,
                                                    "player_id": 1
                                                }
                                            ],
                                            "featured_mod": "faf",
                                            "map_name": "SCMP_001",
                                            "game_options": {
                                                "test": "test"
                                            }
                                        }, correlation_id="9124e8c9-c62f-43c3-bb64-94f3093f2997"
                                        )
    msg = await read_until_command(proto1, "is_ready")
    assert msg == {
        'command': 'is_ready',
        'featured_mod': 'faf',
        'game_name': 'My game name',
        'request_id': '9124e8c9-c62f-43c3-bb64-94f3093f2997',
        'response_time_seconds': 30
    }
