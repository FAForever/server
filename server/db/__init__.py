"""
Database interaction
"""

import asyncio
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection as _AsyncConnection
from sqlalchemy.ext.asyncio import AsyncEngine as _AsyncEngine
from sqlalchemy.util import EMPTY_DICT

from server.metrics import db_exceptions

logger = logging.getLogger(__name__)


@contextmanager
def stat_db_errors():
    """
    Collect metrics on errors thrown
    """
    try:
        yield
    except DBAPIError as e:
        db_exceptions.labels(e.__class__.__name__, e.code).inc()
        raise e


class FAFDatabase:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        db: str = "faf_test",
        **kwargs
    ):
        kwargs["future"] = True
        sync_engine = create_engine(
            f"mysql+aiomysql://{user}:{password}@{host}:{port}/{db}",
            **kwargs
        )

        self.engine = AsyncEngine(sync_engine)

    def acquire(self):
        return self.engine.begin()

    async def close(self):
        await self.engine.dispose()


class AsyncEngine(_AsyncEngine):
    """
    For overriding the connection class used to execute statements.

    This could also be done by changing engine._connection_cls, however this
    is undocumented and probably more fragile so we subclass instead.
    """

    def connect(self):
        return AsyncConnection(self)


class AsyncConnection(_AsyncConnection):
    async def execute(
        self,
        statement,
        parameters=None,
        execution_options=EMPTY_DICT,
        **kwargs
    ):
        with stat_db_errors():
            return await self._execute(
                statement,
                parameters=parameters,
                execution_options=execution_options,
                **kwargs
            )

    async def _execute(
        self,
        statement,
        parameters=None,
        execution_options=EMPTY_DICT,
        **kwargs
    ):
        """
        Wrap strings in the text type automatically and allows bindparams to be
        passed via kwargs.
        """
        if isinstance(statement, str):
            statement = text(statement)

        if kwargs and parameters is None:
            parameters = kwargs

        return await super().execute(
            statement,
            parameters=parameters,
            execution_options=execution_options
        )

    async def stream(
        self,
        statement,
        parameters=None,
        execution_options=EMPTY_DICT,
        **kwargs
    ):
        with stat_db_errors():
            return await self._stream(
                statement,
                parameters=parameters,
                execution_options=execution_options,
                **kwargs
            )

    async def _stream(
        self,
        statement,
        parameters=None,
        execution_options=EMPTY_DICT,
        **kwargs
    ):
        """
        Wrap strings in the text type automatically and allows bindparams to be
        passed via kwargs.
        """
        if isinstance(statement, str):
            statement = text(statement)

        if kwargs and parameters is None:
            parameters = kwargs

        return await super().stream(
            statement,
            parameters=parameters,
            execution_options=execution_options
        )

    async def deadlock_retry_execute(
        self,
        statement,
        parameters=None,
        execution_options=EMPTY_DICT,
        max_attempts=3,
        **kwargs
    ):
        with stat_db_errors():
            return await self._deadlock_retry_execute(
                statement,
                parameters=parameters,
                execution_options=execution_options,
                max_attempts=max_attempts,
                **kwargs
            )

    async def _deadlock_retry_execute(
        self,
        statement,
        parameters=None,
        execution_options=EMPTY_DICT,
        max_attempts=3,
        **kwargs
    ):
        for attempt in range(max_attempts - 1):
            try:
                return await self._execute(
                    statement,
                    parameters=parameters,
                    execution_options=execution_options,
                    **kwargs
                )
            except OperationalError as e:
                error_text = str(e)
                if any(msg in error_text for msg in (
                    "Deadlock found",
                    "Lock wait timeout exceeded"
                )):
                    logger.warning(
                        "Encountered deadlock during SQL execution. Attempts: %d",
                        attempt + 1
                    )
                    # Exponential backoff
                    await asyncio.sleep(0.3 * 2 ** attempt)
                else:
                    raise

        # On the final attempt we don't do any error handling
        return await self._execute(
            statement,
            parameters=parameters,
            execution_options=execution_options,
            **kwargs
        )
