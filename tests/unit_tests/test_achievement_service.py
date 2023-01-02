from unittest import mock

import pytest

from server.config import config
from server.message_queue_service import MessageQueueService
from server.stats.achievement_service import AchievementService


@pytest.fixture
def message_queue_service():
    return mock.create_autospec(MessageQueueService)


@pytest.fixture
def service(message_queue_service):
    return AchievementService(message_queue_service)


def test_fill_queue(service: AchievementService):
    queue = []
    service.unlock("1-2-3", queue)
    service.reveal("2-3-4", queue)
    service.increment("3-4-5", 2, queue)
    service.set_steps_at_least("4-5-6", 3, queue)

    assert queue == [
        {"achievementId": "1-2-3", "operation": "UNLOCK"},
        {"achievementId": "2-3-4", "operation": "REVEAL"},
        {"achievementId": "3-4-5", "operation": "INCREMENT", "steps": 2},
        {"achievementId": "4-5-6", "operation": "SET_STEPS_AT_LEAST", "steps": 3}
    ]


def test_achievement_zero_steps_increment(service: AchievementService):
    assert service.increment(achievement_id="3-4-5", steps=2, queue=[]) is None
    assert service.increment(achievement_id="3-4-5", steps=0, queue=[]) is None
    assert service.set_steps_at_least(achievement_id="3-4-5", steps=2, queue=[]) is None
    assert service.set_steps_at_least(achievement_id="3-4-5", steps=0, queue=[]) is None


async def test_execute_batch_update(service: AchievementService):
    queue = [
        {"achievementId": "1-2-3", "operation": "UNLOCK"},
        {"achievementId": "2-3-4", "operation": "REVEAL"},
        {"achievementId": "3-4-5", "operation": "INCREMENT", "steps": 2},
        {"achievementId": "4-5-6", "operation": "SET_STEPS_AT_LEAST", "steps": 3}
    ]

    await service.execute_batch_update(3, queue)

    service.message_queue_service.publish_many.assert_called_once_with(
        config.MQ_EXCHANGE_NAME,
        "request.achievement.update",
        [
            {"playerId": 3, "achievementId": "1-2-3", "operation": "UNLOCK"},
            {"playerId": 3, "achievementId": "2-3-4", "operation": "REVEAL"},
            {"playerId": 3, "achievementId": "3-4-5", "operation": "INCREMENT", "steps": 2},
            {"playerId": 3, "achievementId": "4-5-6", "operation": "SET_STEPS_AT_LEAST", "steps": 3}
        ]
    )
