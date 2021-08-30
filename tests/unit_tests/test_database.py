from unittest import mock

import asynctest
import pymysql
import pytest
from sqlalchemy.exc import OperationalError

from server.db import AsyncConnection
from tests.utils import fast_forward


@pytest.mark.asyncio
@fast_forward(10)
async def test_deadlock_retry_execute():
    mock_conn = mock.Mock()
    mock_conn.execute = asynctest.CoroutineMock(
        side_effect=OperationalError(
            "QUERY", {}, pymysql.err.OperationalError(-1, "Deadlock found")
        )
    )

    with pytest.raises(OperationalError):
        await AsyncConnection.deadlock_retry_execute(mock_conn, "foo")

    assert mock_conn.execute.call_count == 3


@pytest.mark.asyncio
@fast_forward(10)
async def test_deadlock_retry_execute_success():
    call_count = 0

    async def execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            raise OperationalError(
                "QUERY", {}, pymysql.err.OperationalError(-1, "Deadlock found")
            )

    mock_conn = mock.Mock()
    mock_conn.execute = asynctest.CoroutineMock(side_effect=execute)

    await AsyncConnection.deadlock_retry_execute(mock_conn, "foo")

    assert mock_conn.execute.call_count == 2
