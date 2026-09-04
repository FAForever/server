import asyncio
from unittest import mock

import aio_pika
import pytest

from server.message_queue_service import MessageQueueService


@pytest.fixture
async def mq_service():
    service = MessageQueueService()
    await service.initialize()

    await service.declare_exchange("test_exchange")

    yield service

    await service.shutdown()


async def test_initialize():
    service = MessageQueueService()
    await service.initialize()
    await service.shutdown()


async def test_publish(mq_service):
    payload = {"msg": "test message"}
    exchange_name = "test_exchange"
    routing_key = "test.routing.key"
    delivery_mode = aio_pika.DeliveryMode.NOT_PERSISTENT

    await mq_service.publish(exchange_name, routing_key, payload, delivery_mode)


async def test_incorrect_port(mocker, caplog):
    mocker.patch("server.message_queue_service.config.MQ_PORT", 1)
    service = MessageQueueService()

    await service.initialize()

    expected_warning = "Unable to connect to RabbitMQ. Is it running?"
    assert expected_warning in caplog.messages


async def test_declare_queue_and_consume(mq_service):
    received = asyncio.Event()
    captured: dict = {}

    async def callback(message):
        async with message.process():
            captured["body"] = message.body
            captured["headers"] = dict(message.headers or {})
            received.set()

    result = await mq_service.declare_queue_and_consume(
        exchange_name="test_exchange",
        routing_key="consume.test",
        callback=callback,
    )
    assert result is not None
    queue, consumer_tag = result
    assert consumer_tag

    await mq_service.publish(
        "test_exchange",
        "consume.test",
        {"hello": "world"},
        delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
    )

    await asyncio.wait_for(received.wait(), timeout=5)
    assert captured["body"] == b'{"hello": "world"}'

    await queue.cancel(consumer_tag)


async def test_declare_queue_and_consume_unknown_exchange(mq_service):
    async def callback(_message):
        pass

    with pytest.raises(KeyError):
        await mq_service.declare_queue_and_consume(
            exchange_name="not_declared",
            routing_key="anything",
            callback=callback,
        )


async def test_declare_queue_and_consume_not_ready(mocker, caplog):
    from server.message_queue_service import ConnectionAttemptFailed

    service = MessageQueueService()
    service._connect = mock.AsyncMock(side_effect=ConnectionAttemptFailed)

    async def callback(_message):
        pass

    result = await service.declare_queue_and_consume(
        exchange_name="test_exchange",
        routing_key="x",
        callback=callback,
    )
    assert result is None


async def test_several_initializations_connect_only_once():
    service = MessageQueueService()

    def set_mock_connection(*args, **kwargs):
        service._connection = mock.Mock()
        service._channel = mock.Mock()
        service._channel.declare_exchange = mock.AsyncMock()

    service._connect = mock.AsyncMock(side_effect=set_mock_connection)

    await asyncio.gather(
        service.declare_exchange("exchange_one"),
        service.initialize(),
        service.declare_exchange("exchange_two"),
        service.initialize(),
    )

    service._connect.assert_called_once()
