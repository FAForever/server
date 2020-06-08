import aio_pika
import pytest

from server.message_queue_service import MessageQueueService

pytestmark = pytest.mark.asyncio


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
    assert expected_warning in [rec.message for rec in caplog.records]
