import pytest

from asynctest import CoroutineMock
from server.async_functions import gather_without_exceptions

pytestmark = pytest.mark.asyncio


class CustomError(Exception):
    pass


async def raises_connection_error():
    raise ConnectionError("Test ConnectionError")


async def raises_connection_reset_error():
    raise ConnectionResetError("Test ConnectionResetError")


async def raises_custom_error():
    raise CustomError("Test Exception")


async def test_gather_without_exceptions():
    completes_correctly = CoroutineMock()

    with pytest.raises(CustomError):
        await gather_without_exceptions([
            raises_connection_error(),
            raises_custom_error(),
            completes_correctly()
        ], ConnectionError)

    completes_correctly.assert_called_once()


async def test_gather_without_exceptions_subclass():
    completes_correctly = CoroutineMock()

    await gather_without_exceptions([
        raises_connection_error(),
        raises_connection_reset_error(),
        completes_correctly()
    ], ConnectionError)

    completes_correctly.assert_called_once()
