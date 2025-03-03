from unittest import mock

import pymysql
import pytest
from sqlalchemy.exc import OperationalError

from server.config import config
from server.db import (
    FLYWAY_MINIMUM_REQUIRED_VERSION,
    AsyncConnection,
    get_and_validate_database_version
)
from server.db.models import get_flyway_schema_history_table
from tests.utils import fast_forward


@pytest.fixture(scope="session")
def flyway_schema_history_table():
    return get_flyway_schema_history_table("mock_flyway_schema_history")


@pytest.fixture
async def flyway_schema_history_table_setup(
    database,
    flyway_schema_history_table,
):
    async with database.acquire() as conn:
        await conn.run_sync(flyway_schema_history_table.create, database.engine)

    return flyway_schema_history_table


@fast_forward(10)
async def test_deadlock_retry_execute():
    mock_conn = mock.Mock()
    mock_conn._execute = mock.AsyncMock(
        side_effect=OperationalError(
            "QUERY", {}, pymysql.err.OperationalError(-1, "Deadlock found")
        )
    )

    with pytest.raises(OperationalError):
        await AsyncConnection._deadlock_retry_execute(mock_conn, "foo")

    assert mock_conn._execute.call_count == 3


@fast_forward(10)
async def test_deadlock_retry_execute_success():
    call_count = 0

    async def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            raise OperationalError(
                "QUERY", {}, pymysql.err.OperationalError(-1, "Deadlock found")
            )

    mock_conn = mock.Mock()
    mock_conn._execute = mock.AsyncMock(side_effect=_execute)

    await AsyncConnection._deadlock_retry_execute(mock_conn, "foo")

    assert mock_conn._execute.call_count == 2


async def test_get_and_validate_database_version(
    database,
    flyway_schema_history_table_setup,
    monkeypatch,
):
    current_version = FLYWAY_MINIMUM_REQUIRED_VERSION + 1
    async with database.acquire() as conn:
        await conn.execute(
            flyway_schema_history_table_setup.insert().values(
                version="1",
                success=True,
            ).values(
                version="100",
                success=True,
            ).values(
                version="1000000",
                success=False,
            ).values(
                version=str(current_version),
                success=True,
            ),
        )

    table_name = flyway_schema_history_table_setup.name
    monkeypatch.setattr(config, "DB_FLYWAY_TABLE", table_name)

    version = await get_and_validate_database_version(database)

    assert version is not None
    assert version == current_version


async def test_get_and_validate_database_version_empty(
    database,
    flyway_schema_history_table_setup,
    monkeypatch,
):
    table_name = flyway_schema_history_table_setup.name
    monkeypatch.setattr(config, "DB_FLYWAY_TABLE", table_name)

    with pytest.raises(RuntimeError, match="No successful database migrations"):
        await get_and_validate_database_version(database)


async def test_get_and_validate_database_version_too_low(
    database,
    flyway_schema_history_table_setup,
    monkeypatch,
):
    async with database.acquire() as conn:
        await conn.execute(
            flyway_schema_history_table_setup.insert().values(
                version="1",
                success=True,
            ),
        )

    table_name = flyway_schema_history_table_setup.name
    monkeypatch.setattr(config, "DB_FLYWAY_TABLE", table_name)

    with pytest.raises(RuntimeError, match="does not meet minimum requirement"):
        await get_and_validate_database_version(database)


async def test_get_and_validate_database_version_disabled(
    database,
    monkeypatch,
):
    monkeypatch.setattr(config, "DB_FLYWAY_TABLE", "")
    version = await get_and_validate_database_version(database)

    assert version is None
