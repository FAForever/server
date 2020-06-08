import asyncio

import aio_pika
import pytest

import mock
from server.config import config
from server.decorators import with_logger
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


async def test_incorrect_credentials(mocker):
    mocker.patch("server.message_queue_service.config.MQ_PASSWORD", "bad_password")
    service = MessageQueueService()
    service._logger = mock.Mock()

    await service.initialize()
    service._logger.warning.assert_called_once()

    await service.declare_exchange("test_exchange")
    assert service._logger.warning.call_count == 2

    payload = {"msg": "test message"}
    exchange_name = "test_exchange"
    routing_key = "test.routing.key"
    delivery_mode = aio_pika.DeliveryMode.NOT_PERSISTENT
    await service.publish(exchange_name, routing_key, payload, delivery_mode)
    assert service._logger.warning.call_count == 3

    await service.shutdown()


async def test_incorrect_username(mocker):
    mocker.patch("server.message_queue_service.config.MQ_USER", "bad_user")
    service = MessageQueueService()
    service._logger = mock.Mock()

    await service.initialize()
    service._logger.warning.assert_called()


async def test_incorrect_port(mocker):
    mocker.patch("server.message_queue_service.config.MQ_PORT", 1)
    service = MessageQueueService()
    service._logger = mock.Mock()

    await service.initialize()
    service._logger.warning.assert_called()


async def test_incorrect_vhost(mocker):
    mocker.patch("server.message_queue_service.config.MQ_VHOST", "bad_vhost")
    service = MessageQueueService()
    service._logger = mock.Mock()

    await service.initialize()
    service._logger.warning.assert_called()
