import asyncio

import aio_pika
import pytest

import mock
from server.config import config
from server.decorators import with_logger
from server.messagequeue_service import MessageQueueService

pytestmark = pytest.mark.asyncio


@with_logger
class Consumer:
    def __init__(self):
        self._callback = mock.Mock()

    async def initialize(self):
        self.connection = await aio_pika.connect(
            "amqp://{user}:{password}@localhost/{vhost}".format(
                user=config.MQ_USER, password=config.MQ_PASSWORD, vhost=config.MQ_VHOST
            )
        )
        channel = await self.connection.channel()
        exchange = await channel.declare_exchange(
            "test_exchange", aio_pika.ExchangeType.TOPIC
        )
        self.queue = await channel.declare_queue("test_queue", durable=True)

        await self.queue.bind(exchange, routing_key="#")
        self.consumer_tag = await self.queue.consume(self.callback, exclusive=True)

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

    previous_message_count = consumer.callback_count()
    await asyncio.sleep(0.1)

    assert consumer.callback_count() == previous_message_count + 1
