import asyncio
import json
from unittest.mock import Mock

import pytest

from server.api.api_accessor import ApiAccessor
from server.stats.achievement_service import AchievementService
from tests import CoroMock


@pytest.fixture()
def api_accessor():
    m = Mock(spec=ApiAccessor)
    m.update_achievements = CoroMock()
    return m


@pytest.fixture()
def service(api_accessor: ApiAccessor):
    return AchievementService(api_accessor)


@pytest.fixture()
def create_queue():
    return [
        dict(achievement_id='1-2-3', update_type='UNLOCK'),
        dict(achievement_id='2-3-4', update_type='REVEAL'),
        dict(achievement_id='3-4-5', update_type='INCREMENT', steps=2),
        dict(achievement_id='4-5-6', update_type='SET_STEPS_AT_LEAST', steps=3)
    ]


async def test_fill_queue(service: AchievementService):
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


async def test_api_broken(service: AchievementService):
    queue = create_queue()
    service.api_accessor.update_achievements = CoroMock(return_value=(500, None))
    result = await service.execute_batch_update(42, queue)
    assert result is None


async def test_update_multiple(service: AchievementService):
    content = '''
        {"data": [
            {"attributes": {"achievementId": "1-2-3", "state": "UNLOCKED", "newlyUnlocked": true}},
            {"attributes": {"achievementId": "2-3-4", "state": "REVEALED", "newlyUnlocked": false}},
            {"attributes": {"achievementId": "3-4-5", "state": "LOCKED", "steps": 2, "newlyUnlocked": false}},
            {"attributes": {"achievementId": "4-5-6", "state": "UNLOCKED", "steps": 50, "newlyUnlocked": false}}
        ]}
    '''

    service.api_accessor.update_achievements.coro.return_value = (200, content)

    queue = create_queue()
    result = await service.execute_batch_update(42, queue)

    achievements_data = []
    for achievement in json.loads(content)['data']:
        converted_achievement = dict(
            achievement_id=achievement['attributes']['achievementId'],
            current_state=achievement['attributes']['state'],
            newly_unlocked=achievement['attributes']['newlyUnlocked']
        )
        if 'steps' in achievement['attributes']:
            converted_achievement['current_steps'] = achievement['attributes']['steps']

        achievements_data.append(converted_achievement)

    assert result == achievements_data

    service.api_accessor.update_achievements.assert_called_once_with(queue,42)


async def test_achievement_zero_steps_increment(service: AchievementService):
    assert service.increment(achievement_id='3-4-5', steps=2, queue=[]) is None
    assert service.set_steps_at_least(achievement_id='3-4-5', steps=2, queue=[]) is None

