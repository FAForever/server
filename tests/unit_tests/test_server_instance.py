import asyncio
from unittest import mock

from server import GameService, PlayerService, ServerInstance


def test_auto_create_services():
    instance = ServerInstance("TestCreateServices", None, None, None)

    assert instance.services != {}
    assert isinstance(instance.services["player_service"], PlayerService)
    assert isinstance(instance.services["game_service"], GameService)


async def test_instance_listen():
    mq_service = mock.Mock()
    mq_service.initialize = mock.AsyncMock()
    mq_service.shutdown = mock.AsyncMock()
    mq_service.declare_queue_and_consume = mock.AsyncMock(
        return_value=(mock.Mock(), "tag")
    )
    mq_service.publish = mock.AsyncMock()

    instance = ServerInstance(
        "TestInstanceListen",
        None,
        asyncio.get_running_loop(),
        _override_services={"message_queue_service": mq_service},
    )

    ctx = await instance.listen(
        client_exchange="test-client-ex",
        session_exchange="test-session-ex",
        session_request_exchange="test-session-request-ex"
    )

    assert ctx in instance.contexts
    assert mq_service.declare_queue_and_consume.await_count == 2
    await instance.shutdown()
