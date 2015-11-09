import asyncio
import json
from unittest.mock import Mock, MagicMock

import pytest

from server.api.api_accessor import ApiAccessor
from server.stats.achievement_service import AchievementService
from tests.utils import CoroMock


@pytest.fixture()
def api_accessor():
    m = Mock(spec=ApiAccessor)
    m.api_post = CoroMock()
    return m


@pytest.fixture()
def service(api_accessor: ApiAccessor):
    return AchievementService(api_accessor)

async def test_update_multiple(service: AchievementService):
    content = '''{"updated_achievements": [
        { "achievement_id": "1-2-3", "current_state": "UNLOCKED", "newly_unlocked": true},
        { "achievement_id": "2-3-4", "current_state": "REVEALED", "newly_unlocked": false},
        { "achievement_id": "3-4-5", "current_state": "LOCKED", "current_steps": 2, "newly_unlocked": false},
        { "achievement_id": "4-5-6", "current_state": "UNLOCKED", "current_steps": 50, "newly_unlocked": false}
    ]}'''
    service.api_accessor.api_post.coro.return_value = (None, content)

    queue = []
    service.unlock('1-2-3', queue)
    service.reveal('2-3-4', queue)
    service.increment('3-4-5', 2, queue)
    service.set_steps_at_least('4-5-6', 3, queue)

    assert queue == [
        dict(achievement_id='1-2-3', update_type='UNLOCK'),
        dict(achievement_id='2-3-4', update_type='REVEAL'),
        dict(achievement_id='3-4-5', update_type='INCREMENT', steps=2),
        dict(achievement_id='4-5-6', update_type='SET_STEPS_AT_LEAST', steps=3)
    ]

    result = await service.execute_batch_update(42, queue)
    assert result == json.loads(content)['updated_achievements']

    service.api_accessor.api_post.assert_called_once_with("/achievements/updateMultiple", 42, body=dict(updates=queue))
