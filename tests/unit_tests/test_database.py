from unittest import mock

import asynctest
import pymysql
import pytest

from server.db import deadlock_retry_execute
from tests.utils import fast_forward


@pytest.mark.asyncio
@fast_forward(10)
async def test_deadlock_retry_execute():
    mock_conn = mock.Mock()
    mock_conn.execute = asynctest.CoroutineMock(
        side_effect=pymysql.err.OperationalError(-1, "Deadlock found")
    )

    with pytest.raises(pymysql.err.OperationalError):
        await deadlock_retry_execute(mock_conn, "foo")

    assert mock_conn.execute.call_count == 3


@pytest.mark.asyncio
@fast_forward(10)
async def test_deadlock_retry_execute_success():
    call_count = 0

    async def execute(*args):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            raise pymysql.err.OperationalError(-1, "Deadlock found")

    mock_conn = mock.Mock()
    mock_conn.execute = asynctest.CoroutineMock(side_effect=execute)

    await deadlock_retry_execute(mock_conn, "foo")

    assert mock_conn.execute.call_count == 2
