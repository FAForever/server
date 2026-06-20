import json
from unittest import mock

import pytest

from server.avatar_change_queue_service import (
    PLAYER_AVATAR_UPDATE_ROUTING_KEY,
    AvatarChangeQueueService,
)
from server.config import config


def make_incoming_message(body: bytes):
    """Build a stand-in for aio_pika's IncomingMessage."""
    message = mock.Mock()
    message.body = body

    process_cm = mock.MagicMock()
    process_cm.__aenter__ = mock.AsyncMock(return_value=None)
    process_cm.__aexit__ = mock.AsyncMock(return_value=False)
    message.process = mock.Mock(return_value=process_cm)
    return message


@pytest.fixture
def fake_player_service():
    service = mock.Mock()
    service.refresh_player_avatar = mock.AsyncMock(return_value=True)
    return service


@pytest.fixture
async def avatar_queue_service(fake_player_service):
    queue = mock.Mock()
    queue.cancel = mock.AsyncMock()
    mq_service = mock.Mock()
    mq_service.declare_queue_and_consume = mock.AsyncMock(
        return_value=(queue, "consumer-tag-avatar")
    )
    service = AvatarChangeQueueService(
        message_queue_service=mq_service,
        player_service=fake_player_service,
    )
    await service.initialize()
    yield service
    await service.shutdown()


async def test_shutdown_cancels_consumer(fake_player_service):
    queue = mock.Mock()
    queue.cancel = mock.AsyncMock()
    mq_service = mock.Mock()
    mq_service.declare_queue_and_consume = mock.AsyncMock(
        return_value=(queue, "consumer-tag-xyz")
    )
    service = AvatarChangeQueueService(
        message_queue_service=mq_service,
        player_service=fake_player_service,
    )
    await service.initialize()
    await service.shutdown()

    queue.cancel.assert_awaited_once_with("consumer-tag-xyz")
    assert service._queue is None
    assert service._consumer_tag is None


async def test_shutdown_noop_when_broker_unavailable(fake_player_service):
    mq_service = mock.Mock()
    mq_service.declare_queue_and_consume = mock.AsyncMock(return_value=None)
    service = AvatarChangeQueueService(
        message_queue_service=mq_service,
        player_service=fake_player_service,
    )
    await service.initialize()
    await service.shutdown()


async def test_initialize_declares_consumer(avatar_queue_service):
    mq = avatar_queue_service.message_queue_service
    mq.declare_queue_and_consume.assert_awaited_once()
    kwargs = mq.declare_queue_and_consume.await_args.kwargs
    assert kwargs["exchange_name"] == config.MQ_EXCHANGE_NAME
    assert kwargs["routing_key"] == PLAYER_AVATAR_UPDATE_ROUTING_KEY
    assert kwargs["callback"] == avatar_queue_service._on_message


async def test_refresh_called_for_valid_payload(
    avatar_queue_service, fake_player_service
):
    msg = make_incoming_message(
        json.dumps({"player_id": 42, "avatar_id": 5}).encode()
    )

    await avatar_queue_service._on_message(msg)

    fake_player_service.refresh_player_avatar.assert_awaited_once_with(42)


async def test_refresh_called_when_avatar_cleared(
    avatar_queue_service, fake_player_service
):
    msg = make_incoming_message(
        json.dumps({"player_id": 42, "avatar_id": None}).encode()
    )

    await avatar_queue_service._on_message(msg)

    fake_player_service.refresh_player_avatar.assert_awaited_once_with(42)


async def test_extra_fields_are_tolerated(
    avatar_queue_service, fake_player_service
):
    msg = make_incoming_message(
        json.dumps({"player_id": 7, "avatar_id": 1, "future_field": "ok"}).encode()
    )

    await avatar_queue_service._on_message(msg)

    fake_player_service.refresh_player_avatar.assert_awaited_once_with(7)


async def test_player_not_connected_is_logged(
    avatar_queue_service, fake_player_service, caplog
):
    fake_player_service.refresh_player_avatar = mock.AsyncMock(return_value=False)

    msg = make_incoming_message(
        json.dumps({"player_id": 999, "avatar_id": 1}).encode()
    )

    import logging
    with caplog.at_level(logging.DEBUG):
        await avatar_queue_service._on_message(msg)

    fake_player_service.refresh_player_avatar.assert_awaited_once_with(999)
    assert any("not connected here" in m for m in caplog.messages)


async def test_malformed_json_body_is_dropped(
    avatar_queue_service, fake_player_service, caplog
):
    msg = make_incoming_message(b"definitely not json")

    await avatar_queue_service._on_message(msg)

    fake_player_service.refresh_player_avatar.assert_not_awaited()
    assert any("non-JSON body" in m for m in caplog.messages)


async def test_non_object_json_body_is_dropped(
    avatar_queue_service, fake_player_service
):
    msg = make_incoming_message(b"[1, 2, 3]")

    await avatar_queue_service._on_message(msg)

    fake_player_service.refresh_player_avatar.assert_not_awaited()


async def test_missing_player_id_is_dropped(
    avatar_queue_service, fake_player_service, caplog
):
    msg = make_incoming_message(json.dumps({"avatar_id": 5}).encode())

    await avatar_queue_service._on_message(msg)

    fake_player_service.refresh_player_avatar.assert_not_awaited()
    assert any("invalid player_id" in m for m in caplog.messages)


async def test_non_int_player_id_is_dropped(
    avatar_queue_service, fake_player_service, caplog
):
    msg = make_incoming_message(
        json.dumps({"player_id": "not-an-int", "avatar_id": 5}).encode()
    )

    await avatar_queue_service._on_message(msg)

    fake_player_service.refresh_player_avatar.assert_not_awaited()
    assert any("invalid player_id" in m for m in caplog.messages)
