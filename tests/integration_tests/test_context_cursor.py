import asyncio
from server.db import ContextCursor
from unittest.mock import Mock

def get_coro_mock(return_value):
    @asyncio.coroutine
    def coro_mock(*args, **kwargs):
        return return_value
    return Mock(wraps=coro_mock)

@asyncio.coroutine
def test_context_cursor(mocker, db_pool):
    with (yield from db_pool) as conn:
        with (yield from conn.cursor(ContextCursor)) as cursor:
            cursor.close = get_coro_mock(None)
            print("Derp")
    cursor.close.assert_called_once_with()
