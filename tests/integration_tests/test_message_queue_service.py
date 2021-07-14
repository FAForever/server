import asyncio
from unittest import mock

import aio_pika
import pytest

from server.config import config
from server.decorators import with_logger
from server.message_queue_service import MessageQueueService

pytestmark = [pytest.mark.asyncio, pytest.mark.rabbitmq]


@with_logger
class Consumer:
    def __init__(self):
        self._callback = mock.Mock()

    async def initialize(self):
        self.connection = await aio_pika.connect(
            f"amqp://{config.MQ_USER}:{config.MQ_PASSWORD}@localhost/{config.MQ_VHOST}"
        )
        channel = await self.connection.channel()
        exchange = await channel.declare_exchange(
            "test_exchange", aio_pika.ExchangeType.TOPIC, durable=True
        )
        self.queue = await channel.declare_queue("test_queue", exclusive=True)

        await self.queue.bind(exchange, routing_key="#")
        self.consumer_tag = await self.queue.consume(self.callback)

    def callback(self, message):
        self._logger.debug("Received message %r", message)
        self._callback()

    def callback_count(self):
        return self._callback.call_count

    async def shutdown(self):
        await self.queue.cancel(self.consumer_tag)
        await self.connection.close()


@pytest.fixture
async def mq_service():
    service = MessageQueueService()
    await service.initialize()

    await service.declare_exchange("test_exchange")

    yield service

    await service.shutdown()


@pytest.fixture
async def consumer():
    consumer = Consumer()
    await consumer.initialize()

    yield consumer

    await consumer.shutdown()


async def test_connect(mq_service):
    await mq_service.declare_exchange("test_topic", aio_pika.ExchangeType.TOPIC)

    assert "test_topic" in mq_service._exchanges


async def test_publish_wrong_exchange(mq_service):
    bad_exchange = "nonexistent_exchange"
    with pytest.raises(KeyError):
        await mq_service.publish(bad_exchange, "", {})


async def test_consumer_receives(mq_service, consumer):
    payload = {"msg": "test message"}
    exchange_name = "test_exchange"
    routing_key = "test.routing.key"
    delivery_mode = aio_pika.DeliveryMode.NOT_PERSISTENT

    await mq_service.publish(exchange_name, routing_key, payload, delivery_mode)

    await asyncio.sleep(0.1)

    assert consumer.callback_count() == 1


async def test_reconnect(mq_service):
    await mq_service.declare_exchange("test_topic", aio_pika.ExchangeType.TOPIC)
    await mq_service.declare_exchange("test_direct", aio_pika.ExchangeType.DIRECT)

    await mq_service.reconnect()

    assert "test_topic" in mq_service._exchanges
    assert mq_service._exchange_types["test_topic"] == aio_pika.ExchangeType.TOPIC
    assert "test_direct" in mq_service._exchanges
    assert mq_service._exchange_types["test_direct"] == aio_pika.ExchangeType.DIRECT
    assert mq_service._is_ready


async def test_incorrect_credentials(mocker, caplog):
    mocker.patch("server.message_queue_service.config.MQ_PASSWORD", "bad_password")
    service = MessageQueueService()

    await service.initialize()
    expected_warning = "Unable to connect to RabbitMQ. Incorrect credentials?"
    assert expected_warning in [rec.message for rec in caplog.records]
    assert service._is_ready is False
    caplog.clear()

    await service.declare_exchange("test_exchange")
    expected_warning = "Not connected to RabbitMQ, unable to declare exchange."
    assert expected_warning in [rec.message for rec in caplog.records]
    caplog.clear()

    payload = {"msg": "test message"}
    exchange_name = "test_exchange"
    routing_key = "test.routing.key"
    delivery_mode = aio_pika.DeliveryMode.NOT_PERSISTENT
    await service.publish(exchange_name, routing_key, payload, delivery_mode)
    expected_warning = "Not connected to RabbitMQ, unable to publish message."
    assert expected_warning in [rec.message for rec in caplog.records]

    await service.shutdown()


async def test_incorrect_username(mocker, caplog):
    mocker.patch("server.message_queue_service.config.MQ_USER", "bad_user")
    service = MessageQueueService()

    await service.initialize()

    expected_warning = "Unable to connect to RabbitMQ. Incorrect credentials?"
    assert expected_warning in [rec.message for rec in caplog.records]


async def test_incorrect_vhost(mocker, caplog):
    mocker.patch("server.message_queue_service.config.MQ_VHOST", "bad_vhost")
    service = MessageQueueService()

    await service.initialize()

    assert any("Incorrect vhost?" in rec.message for rec in caplog.records)


async def test_initialize_declare_exchange_race_condition():
    service = MessageQueueService()

    async def keep_declaring_exchanges():
        i = 0
        while service._channel is None:
            await service.declare_exchange(f"exchange_{i}")
            await asyncio.sleep(0)
            i += 1

    await asyncio.gather(keep_declaring_exchanges(), service.initialize())


async def test_declaring_exchange_without_initialization():
    service = MessageQueueService()
    exchange_name = "test_exchange"

    assert service._is_ready is False
    assert service._connection is None

    await service.declare_exchange(exchange_name)

    assert service._is_ready
    assert service._connection is not None
    assert service._exchanges.get(exchange_name) is not None
