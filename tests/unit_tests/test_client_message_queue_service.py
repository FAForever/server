import json
from unittest import mock

import pytest

from server import ServerInstance
from server.client_message_queue_service import (
    CLIENT_NOTIFY_ROUTING_KEY,
    ClientMessageQueueService
)
from server.config import config


def make_incoming_message(body: bytes, headers: dict | None = None):
    """Build a stand-in for aio_pika's IncomingMessage."""
    message = mock.Mock()
    message.body = body
    message.headers = headers

    process_cm = mock.MagicMock()
    process_cm.__aenter__ = mock.AsyncMock(return_value=None)
    process_cm.__aexit__ = mock.AsyncMock(return_value=False)
    message.process = mock.Mock(return_value=process_cm)
    return message


@pytest.fixture
def server_instance():
    return mock.create_autospec(ServerInstance)


@pytest.fixture
def fake_player_service():
    """Stand in for PlayerService supporting __getitem__/__setitem__."""
    class _FakePlayerService:
        def __init__(self):
            self._players = {}

        def __getitem__(self, player_id):
            return self._players.get(player_id)

        def __setitem__(self, player_id, player):
            self._players[player_id] = player

    return _FakePlayerService()


@pytest.fixture
async def client_message_queue_service(server_instance, fake_player_service):
    queue = mock.Mock()
    queue.cancel = mock.AsyncMock()
    mq_service = mock.Mock()
    mq_service.declare_queue_and_consume = mock.AsyncMock(
        return_value=(queue, "consumer-tag-123")
    )
    service = ClientMessageQueueService(
        server=server_instance,
        message_queue_service=mq_service,
        player_service=fake_player_service,
    )
    await service.initialize()
    yield service
    await service.shutdown()


async def test_shutdown_cancels_consumer(
    server_instance, fake_player_service
):
    queue = mock.Mock()
    queue.cancel = mock.AsyncMock()
    mq_service = mock.Mock()
    mq_service.declare_queue_and_consume = mock.AsyncMock(
        return_value=(queue, "consumer-tag-xyz")
    )
    service = ClientMessageQueueService(
        server=server_instance,
        message_queue_service=mq_service,
        player_service=fake_player_service,
    )
    await service.initialize()
    await service.shutdown()

    queue.cancel.assert_awaited_once_with("consumer-tag-xyz")
    assert service._queue is None
    assert service._consumer_tag is None


async def test_shutdown_noop_when_broker_unavailable(
    server_instance, fake_player_service
):
    mq_service = mock.Mock()
    mq_service.declare_queue_and_consume = mock.AsyncMock(return_value=None)
    service = ClientMessageQueueService(
        server=server_instance,
        message_queue_service=mq_service,
        player_service=fake_player_service,
    )
    await service.initialize()
    # Should not raise even though no queue was ever created.
    await service.shutdown()


async def test_initialize_declares_consumer(client_message_queue_service):
    mq = client_message_queue_service.message_queue_service
    mq.declare_queue_and_consume.assert_awaited_once()
    kwargs = mq.declare_queue_and_consume.await_args.kwargs
    assert kwargs["exchange_name"] == config.MQ_EXCHANGE_NAME
    assert kwargs["routing_key"] == CLIENT_NOTIFY_ROUTING_KEY
    assert kwargs["callback"] == client_message_queue_service._on_message


async def test_dispatch_to_connected_user(
    client_message_queue_service, fake_player_service
):
    player = mock.Mock()
    player.write_message = mock.Mock()
    fake_player_service[42] = player

    payload = {"command": "notice", "text": "hi"}
    msg = make_incoming_message(json.dumps(payload).encode(), {"user-id": 42})

    await client_message_queue_service._on_message(msg)

    player.write_message.assert_called_once_with(payload)
    client_message_queue_service.server.write_broadcast.assert_not_called()


async def test_dispatch_to_disconnected_user_is_dropped(
    client_message_queue_service, caplog
):
    payload = {"command": "notice"}
    msg = make_incoming_message(json.dumps(payload).encode(), {"user-id": 999})

    await client_message_queue_service._on_message(msg)

    client_message_queue_service.server.write_broadcast.assert_not_called()
    assert any("not connected here" in m for m in caplog.messages)


async def test_broadcast_when_no_user_id_header(client_message_queue_service):
    payload = {"command": "announcement", "text": "hello world"}
    msg = make_incoming_message(json.dumps(payload).encode(), headers=None)

    await client_message_queue_service._on_message(msg)

    client_message_queue_service.server.write_broadcast.assert_called_once_with(payload)


async def test_broadcast_when_headers_empty(client_message_queue_service):
    payload = {"command": "announcement"}
    msg = make_incoming_message(json.dumps(payload).encode(), headers={})

    await client_message_queue_service._on_message(msg)

    client_message_queue_service.server.write_broadcast.assert_called_once_with(payload)


async def test_malformed_json_body_is_dropped(
    client_message_queue_service, caplog
):
    msg = make_incoming_message(b"not json at all", headers=None)

    await client_message_queue_service._on_message(msg)

    client_message_queue_service.server.write_broadcast.assert_not_called()
    assert any("non-JSON body" in m for m in caplog.messages)


async def test_non_object_json_body_is_dropped(client_message_queue_service):
    msg = make_incoming_message(b"[1, 2, 3]", headers=None)

    await client_message_queue_service._on_message(msg)

    client_message_queue_service.server.write_broadcast.assert_not_called()


async def test_invalid_user_id_header_is_dropped(
    client_message_queue_service, caplog
):
    msg = make_incoming_message(
        json.dumps({"command": "x"}).encode(),
        headers={"user-id": "not-an-int"},
    )

    await client_message_queue_service._on_message(msg)

    client_message_queue_service.server.write_broadcast.assert_not_called()
    assert any("invalid user-id" in m for m in caplog.messages)


async def test_channel_header_currently_drops(
    client_message_queue_service, caplog
):
    msg = make_incoming_message(
        json.dumps({"command": "x"}).encode(),
        headers={"channel": "matchmaker"},
    )

    await client_message_queue_service._on_message(msg)

    client_message_queue_service.server.write_broadcast.assert_not_called()
    assert any("channel routing is not yet implemented" in m for m in caplog.messages)
