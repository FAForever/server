import asyncio
import json
from unittest.mock import Mock, MagicMock

import pytest

from server.api.api_accessor import ApiAccessor
from server.stats.achievement_service import AchievementService
from server.stats.event_service import EventService
from tests import CoroMock


@pytest.fixture()
def api_accessor():
    return Mock(spec=ApiAccessor)


@pytest.fixture()
def service(api_accessor: ApiAccessor):
    return EventService(api_accessor)


async def test_record_multiple(service: EventService):
    content = '''{"updated_events": [
        { "event_id": "1-2-3", "count": 1},
        { "event_id": "2-3-4", "count": 4}
    ]}'''.encode('utf-8')
    service.api_accessor.api_post = CoroMock(return_value=(None, content))

    queue = []
    service.record_event('1-2-3', 1, queue)
    service.record_event('2-3-4', 4, queue)

    assert queue == [
        dict(event_id='1-2-3', count=1),
        dict(event_id='2-3-4', count=4),
    ]

    result = await service.execute_batch_update(42, queue)
    assert result == json.loads(content.decode('utf-8'))['updated_events']

    service.api_accessor.api_post.assert_called_once_with("/events/recordMultiple", 42, data=dict(updates=queue))
