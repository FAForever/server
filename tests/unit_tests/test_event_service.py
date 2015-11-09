import asyncio
import json
from unittest.mock import Mock, MagicMock

import pytest

from server.api.api_accessor import ApiAccessor
from server.stats.achievement_service import AchievementService
from server.stats.event_service import EventService


@pytest.fixture()
def api_accessor():
    return Mock(spec=ApiAccessor)


@pytest.fixture()
def service(api_accessor: ApiAccessor):
    return EventService(api_accessor)


@asyncio.coroutine
def test_record_event_for_player(service: EventService):
    content = '{"count": 2}'
    service.api_accessor.api_post = MagicMock(return_value=(None, content))

    result = yield from service.record_event('1-2-3', 2, player_id=42)
    assert result == dict(count=2)

    service.api_accessor.api_post.assert_called_once_with("/events/1-2-3/record", 42, body=dict(count=2))


@asyncio.coroutine
def test_record_event_for_player_with_zero_count(service: EventService):
    yield from service.record_event('1-2-3', 0, player_id=42)

    assert service.api_accessor.call_count == 0


@asyncio.coroutine
def test_update_multiple(service: EventService):
    content = '''{"updated_events": [
        { "event_id": "1-2-3", "count": 1},
        { "event_id": "2-3-4", "count": 4}
    ]}'''
    service.api_accessor.api_post = MagicMock(return_value=(None, content))

    queue = []
    yield from service.record_event('1-2-3', 1, queue=queue)
    yield from service.record_event('2-3-4', 4, queue=queue)

    assert queue == [
        dict(event_id='1-2-3', count=1),
        dict(event_id='2-3-4', count=4),
    ]

    result = yield from service.execute_batch_update(42, queue)
    assert result == json.loads(content)['updated_events']

    service.api_accessor.api_post.assert_called_once_with("/events/updateMultiple", 42, body=dict(updates=queue))
