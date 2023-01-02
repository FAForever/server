from unittest import mock

import pytest

from server.config import config
from server.message_queue_service import MessageQueueService
from server.stats.event_service import EventService


@pytest.fixture
def message_queue_service():
    return mock.create_autospec(MessageQueueService)


@pytest.fixture
def service(message_queue_service):
    return EventService(message_queue_service)


async def test_fill_queue(service: EventService):
    queue = []
    service.record_event("1-2-3", 0, queue)
    service.record_event("1-2-3", 1, queue)
    service.record_event("2-3-4", 4, queue)

    assert queue == [
        {"eventId": "1-2-3", "count": 1},
        {"eventId": "2-3-4", "count": 4},
    ]


async def test_execute_batch_update(service: EventService):
    queue = [
        {"eventId": "1-2-3", "count": 1},
        {"eventId": "2-3-4", "count": 4},
    ]

    await service.execute_batch_update(3, queue)

    service.message_queue_service.publish_many.assert_called_once_with(
        config.MQ_EXCHANGE_NAME,
        "request.event.update",
        [
            {"playerId": 3, "eventId": "1-2-3", "count": 1},
            {"playerId": 3, "eventId": "2-3-4", "count": 4},
        ]
    )
