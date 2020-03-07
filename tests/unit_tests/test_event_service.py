from unittest.mock import Mock

import pytest
from asynctest import CoroutineMock

from server.api.api_accessor import ApiAccessor
from server.stats.event_service import EventService

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def api_accessor():
    return Mock(spec=ApiAccessor)


@pytest.fixture()
def service(api_accessor: ApiAccessor):
    return EventService(api_accessor)


def create_queue():
    return [
        dict(event_id="1-2-3", count=1),
        dict(event_id="2-3-4", count=4),
    ]


async def test_fill_queue(service: EventService):

    queue = []
    service.record_event("1-2-3", 0, queue)
    service.record_event("1-2-3", 1, queue)
    service.record_event("2-3-4", 4, queue)

    assert queue == [
        dict(event_id="1-2-3", count=1),
        dict(event_id="2-3-4", count=4),
    ]


async def test_api_broken(service: EventService):
    service.api_accessor.update_events = CoroutineMock(return_value=(500, None))
    result = await service.execute_batch_update(42, create_queue())
    assert result is None


async def test_api_broken_2(service: EventService):
    service.api_accessor.update_events = CoroutineMock(side_effect=ConnectionError())
    result = await service.execute_batch_update(42, create_queue())
    assert result is None


async def test_api_broken_2(service: EventService):
    service.api_accessor.update_events = CoroutineMock(side_effect=ConnectionError())
    result = await service.execute_batch_update(42, create_queue())
    assert result is None


async def test_record_multiple(service: EventService):

    content = {
        "data": [
            {"attributes": {"eventId": "1-2-3", "currentCount": 1}},
            {"attributes": {"eventId": "2-3-4", "currentCount": 4}}
        ]
    }

    queue = create_queue()

    service.api_accessor.update_events = CoroutineMock(return_value=(200, content))
    result = await service.execute_batch_update(42, queue)

    events_data = []
    for event in content["data"]:
        converted_event = dict(
            event_id=event["attributes"]["eventId"],
            count=event["attributes"]["currentCount"]
        )
        events_data.append(converted_event)

    assert result == events_data

    service.api_accessor.update_events.assert_called_once_with(queue, 42)
