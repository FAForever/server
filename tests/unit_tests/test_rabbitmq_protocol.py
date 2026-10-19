import asyncio
from unittest import mock

import pytest

from server.config import config
from server.protocol import DisconnectedError, RabbitMQProtocol


def make_incoming_message(body: bytes | dict, headers: dict | None = None):
    """Build a mock aio_pika IncomingMessage."""
    message = mock.Mock()
    message.body = body
    message.headers = headers

    process_cm = mock.MagicMock()
    process_cm.__aenter__ = mock.AsyncMock(return_value=None)
    process_cm.__aexit__ = mock.AsyncMock(return_value=False)
    message.process = mock.Mock(return_value=process_cm)
    return message


async def test_read_message_from_asyncio_queue_dict():
    queue = asyncio.Queue()
    mq_service = mock.Mock()

    proto = RabbitMQProtocol(queue=queue, server_context=mq_service, session=0)
    await queue.put({"command": "pong", "count": 1})

    assert await proto.read_message() == {"command": "pong", "count": 1}
    await proto.close()


async def test_read_message_when_closed_raises():
    queue = asyncio.Queue()
    proto = RabbitMQProtocol(queue=queue, server_context=mock.Mock(), session=0)
    await proto.close()

    with pytest.raises(DisconnectedError):
        await proto.read_message()


async def test_read_message_unblocks_on_close():
    queue = asyncio.Queue()
    proto = RabbitMQProtocol(queue=queue, server_context=mock.Mock(), session=0)

    async def close_later():
        await asyncio.sleep(0.05)
        await proto.close()

    asyncio.create_task(close_later())

    with pytest.raises(DisconnectedError):
        await proto.read_message()


async def test_read_message_unblocks_on_abort():
    queue = asyncio.Queue()
    proto = RabbitMQProtocol(queue=queue, server_context=mock.Mock(), session=0)

    async def abort_later():
        await asyncio.sleep(0.05)
        proto.abort()

    asyncio.create_task(abort_later())

    with pytest.raises(DisconnectedError):
        await proto.read_message()


async def test_send_message_publishes_via_message_queue_service():
    mq_service = mock.Mock()
    mq_service.publish = mock.AsyncMock()

    proto = RabbitMQProtocol(
        queue=asyncio.Queue(),
        server_context=mq_service,
        session=0,
    )

    await proto.send_message({"command": "login", "user": "alice"})

    mq_service.publish.assert_awaited_once_with(
        exchange_name=config.OUTBOUND_EXCHANGE_NAME,
        routing="",
        payload={"message": {"command": "login", "user": "alice"}, "target": {"@type": "session", "session_id": 0}},
    )
    await proto.close()


async def test_send_messages_publishes_all():
    mq_service = mock.Mock()
    mq_service.publish_many = mock.AsyncMock()

    proto = RabbitMQProtocol(
        queue=asyncio.Queue(),
        server_context=mq_service,
        session=0
    )
    payloads = [{"a": 1}, {"b": 2}, {"c": 3}]
    await proto.send_messages(payloads)

    mq_service.publish_many.assert_awaited_once_with(
        exchange_name=config.OUTBOUND_EXCHANGE_NAME,
        routing="",
        payloads=[{"message": {"a": 1}, "target": {"@type": "session", "session_id": 0}}, {"message": {"b": 2}, "target": {"@type": "session", "session_id": 0}}, {"message": {"c": 3}, "target": {"@type": "session", "session_id": 0}}],
    )
    await proto.close()


async def test_write_message_and_drain():
    mq_service = mock.Mock()
    mq_service.publish = mock.AsyncMock()

    proto = RabbitMQProtocol(
        queue=asyncio.Queue(),
        server_context=mq_service,
        session=0
    )
    proto.write_message({"command": "ping"})
    await proto.drain()

    mq_service.publish.assert_awaited_once_with(
        exchange_name=config.OUTBOUND_EXCHANGE_NAME,
        routing="",
        payload={"message": {"command": "ping"}, "target": {"@type": "session", "session_id": 0}},
    )
    await proto.close()


async def test_write_messages_and_drain():
    mq_service = mock.Mock()
    mq_service.publish_many = mock.AsyncMock()

    proto = RabbitMQProtocol(
        queue=asyncio.Queue(),
        server_context=mq_service,
        session=0
    )
    proto.write_messages([{"msg": 1}, {"msg": 2}])
    await proto.drain()

    mq_service.publish_many.assert_awaited_once_with(
        exchange_name=config.OUTBOUND_EXCHANGE_NAME,
        routing="",
        payloads=[{"message": {"msg": 1}, "target": {"@type": "session", "session_id": 0}}, {"message": {"msg": 2}, "target": {"@type": "session", "session_id": 0}}],
    )
    await proto.close()


async def test_write_raw_when_disconnected_raises():
    proto = RabbitMQProtocol(
        queue=asyncio.Queue(),
        server_context=mock.Mock(),
        session=0
    )
    await proto.close()

    with pytest.raises(DisconnectedError):
        proto.write_raw(b'{"command":"ping"}')


async def test_write_message_when_disconnected_raises():
    proto = RabbitMQProtocol(
        queue=asyncio.Queue(),
        server_context=mock.Mock(),
        session=0,
    )
    await proto.close()

    with pytest.raises(DisconnectedError):
        proto.write_message({"command": "ping"})


async def test_drain_raises_disconnected_on_publish_error():
    mq_service = mock.Mock()
    mq_service.publish = mock.AsyncMock(side_effect=ConnectionError("Broker unavailable"))

    proto = RabbitMQProtocol(queue=asyncio.Queue(), server_context=mq_service, session=0)
    proto.write_message({"command": "test"})

    with pytest.raises(DisconnectedError):
        await proto.drain()

    assert proto.is_connected() is False


async def test_send_raw():
    mq_service = mock.Mock()
    mq_service.publish = mock.AsyncMock()

    proto = RabbitMQProtocol(queue=asyncio.Queue(), server_context=mq_service, session=0)
    await proto.send_raw(b'{"raw":"data"}')

    mq_service.publish.assert_awaited_once_with(
        exchange_name=config.OUTBOUND_EXCHANGE_NAME,
        routing="",
        payload={"message": {"raw": "data"}, "target": {"@type": "session", "session_id": 0}},
    )
    await proto.close()


async def test_drain_empty_pending_noop():
    proto = RabbitMQProtocol(queue=asyncio.Queue(), server_context=mock.Mock(), session=0)
    await proto.drain()
    await proto.close()
