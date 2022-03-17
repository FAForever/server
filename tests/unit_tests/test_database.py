from unittest import mock

import pymysql
import pytest
from sqlalchemy.exc import OperationalError

from server.db import AsyncConnection
from tests.utils import fast_forward


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
