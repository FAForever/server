"""
Database interaction
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection as _AsyncConnection
from sqlalchemy.ext.asyncio import AsyncEngine as _AsyncEngine
from sqlalchemy.util import EMPTY_DICT

logger = logging.getLogger(__name__)


class FAFDatabase:
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None

    async def connect(
        self,
        host="localhost",
        port=3306,
        user="root",
        password="",
        db="faf_test",
        **kwargs
    ):
        if self.engine is not None:
            raise ValueError("DB is already connected!")

        kwargs["future"] = True
        sync_engine = create_engine(
            f"mysql+aiomysql://{user}:{password}@{host}:{port}/{db}",
            **kwargs
        )

        self.engine = AsyncEngine(sync_engine)

    def acquire(self):
        assert self.engine is not None, "must call `connect` before `acquire`!"
        return self.engine.begin()

    async def close(self):
        assert self.engine is not None, "must call `connect` before `close`!"
        await self.engine.dispose()
        self.engine = None


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
    ):
        """
        Wrap strings in the text type automatically
        """
        if isinstance(statement, str):
            statement = text(statement)

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
    ):
        """
        Wrap strings in the text type automatically
        """
        if isinstance(statement, str):
            statement = text(statement)

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
        max_attempts=3
    ):
        for attempt in range(max_attempts - 1):
            try:
                return await self.execute(
                    statement,
                    parameters=parameters,
                    execution_options=execution_options
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
        return await self.execute(
            statement,
            parameters=parameters,
            execution_options=execution_options
        )
