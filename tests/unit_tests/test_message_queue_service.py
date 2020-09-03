import asyncio
from unittest import mock

import aio_pika
import pytest
from asynctest import CoroutineMock

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


async def test_several_initializations_connect_only_once():
    service = MessageQueueService()

    def set_mock_connection(*args, **kwargs):
        service._connection = mock.Mock()
        service._channel = mock.Mock()
        service._channel.declare_exchange = CoroutineMock()

    service._connect = CoroutineMock(side_effect=set_mock_connection)

    await asyncio.gather(
        service.declare_exchange("exchange_one"),
        service.initialize(),
        service.declare_exchange("exchange_two"),
        service.initialize(),
    )

    service._connect.assert_called_once()
