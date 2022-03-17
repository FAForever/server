from datetime import datetime, timedelta, timezone

import pytest

from server.ladder_service.violation_service import Violation, ViolationService

NOW = datetime(2020, 1, 1, tzinfo=timezone.utc)
IMPORT_PATH_NOW = "server.ladder_service.violation_service.datetime_now"


@pytest.fixture
async def violation_service(mocker):
    mocker.patch(IMPORT_PATH_NOW, return_value=NOW)
    service = ViolationService()
    await service.initialize()
    yield service
    await service.shutdown()


def test_violation_class():
    assert Violation(count=10, time=NOW) == Violation(count=10, time=NOW)
    assert Violation(count=10, time=NOW) != Violation(count=15, time=NOW)
    assert Violation(count=10, time=NOW) != Violation(count=10, time=NOW + timedelta(minutes=5))


def test_violation_ban_times():
    assert Violation(count=0, time=NOW).get_ban_expiration() == NOW
    assert Violation(count=1, time=NOW).get_ban_expiration() == NOW
    assert Violation(count=2, time=NOW).get_ban_expiration() == NOW + timedelta(minutes=10)
    assert Violation(count=3, time=NOW).get_ban_expiration() == NOW + timedelta(minutes=30)
    assert Violation(count=4, time=NOW).get_ban_expiration() == NOW + timedelta(minutes=30)


def test_violation_is_expired(mocker):
    mocker.patch(IMPORT_PATH_NOW, return_value=NOW)

    violation = Violation(count=1, time=NOW)

    assert violation.is_expired() is False
    assert violation.is_expired(NOW) is False

    violation.time = NOW - timedelta(hours=1)

    assert violation.is_expired() is True
    assert violation.is_expired(NOW) is True

    violation.time = NOW - timedelta(hours=2)

    assert violation.is_expired() is True
    assert violation.is_expired(NOW) is True


def test_violation_clear_expired(
    violation_service: ViolationService,
    player_factory
):
    p1 = player_factory("Test1", player_id=1)
    p2 = player_factory("Test2", player_id=2)

    v1 = Violation(time=NOW - timedelta(hours=1))
    v2 = Violation(time=NOW)

    violation_service.violations[p1] = v1
    violation_service.violations[p2] = v2

    violation_service.clear_expired()

    assert violation_service.violations == {p2: v2}


def test_register_violation(
    violation_service: ViolationService,
    player_factory
):
    p1 = player_factory("Test1", player_id=1)
    p2 = player_factory("Test2", player_id=2)

    violation_service.register_violations([p1])
    assert violation_service.get_violations([p1, p2]) == {}

    violation_service.register_violations([p1])
    assert violation_service.get_violations([p1, p2]) == {
        p1: Violation(count=2, time=NOW)
    }


def test_get_violations_clears_expired(
    violation_service: ViolationService,
    player_factory
):
    p1 = player_factory("Test3", player_id=1)

    violation_service.violations[p1] = Violation(time=NOW - timedelta(hours=1))
    violation_service.get_violations([p1])
    assert violation_service.violations == {}
