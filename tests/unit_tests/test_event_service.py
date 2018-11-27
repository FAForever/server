import asyncio
import json
from unittest.mock import Mock, MagicMock

import pytest

from server.api.api_accessor import ApiAccessor
from server.stats.event_service import EventService
from tests import CoroMock


@pytest.fixture()
def api_accessor():
    return Mock(spec=ApiAccessor)


@pytest.fixture()
def service(api_accessor: ApiAccessor):
    return EventService(api_accessor)


@pytest.fixture()
def create_queue():
    return [
        dict(event_id='1-2-3', count=1),
        dict(event_id='2-3-4', count=4),
    ]


async def test_fill_queue(service: EventService):

    queue = []
    service.record_event('1-2-3', 1, queue)
    service.record_event('2-3-4', 4, queue)

    assert queue == [
        dict(event_id='1-2-3', count=1),
        dict(event_id='2-3-4', count=4),
    ]


async def test_api_broken(service: EventService):
    service.api_accessor.update_events = CoroMock(return_value=(500, None))
    result = await service.execute_batch_update(42, create_queue())
    assert result is None


async def test_record_multiple(service: EventService):

    content = '''
        {"data": [
            {"attributes": {"eventId": "1-2-3", "count": 1}},
            {"attributes": {"eventId": "2-3-4", "count": 4}}
        ]}
    '''

    queue = create_queue()

    service.api_accessor.update_events = CoroMock(return_value=(200, content))
    result = await service.execute_batch_update(42, queue)

    events_data = []
    for event in json.loads(content)['data']:
        converted_event = dict(
            event_id=event['attributes']['eventId'],
            count=event['attributes']['count']
        )
        events_data.append(converted_event)

    assert result == events_data

    service.api_accessor.update_events.assert_called_once_with(queue, 42)

