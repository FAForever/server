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


async def test_incorrect_credentials(mocker, caplog):
    mocker.patch("server.message_queue_service.config.MQ_PASSWORD", "bad_password")
    service = MessageQueueService()

    await service.initialize()
    expected_warning = "Unable to connect to RabbitMQ. Incorrect credentials?"
    assert expected_warning in [rec.message for rec in caplog.records]
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


async def test_incorrect_port(mocker, caplog):
    mocker.patch("server.message_queue_service.config.MQ_PORT", 1)
    service = MessageQueueService()

    await service.initialize()

    expected_warning = "Unable to connect to RabbitMQ. Is it running?"
    assert expected_warning in [rec.message for rec in caplog.records]


async def test_incorrect_vhost(mocker, caplog):
    mocker.patch("server.message_queue_service.config.MQ_VHOST", "bad_vhost")
    service = MessageQueueService()

    await service.initialize()

    assert any("Incorrect vhost?" in rec.message for rec in caplog.records)
