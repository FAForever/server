import asyncio
import logging

from aiomysql.sa import create_engine
from pymysql.err import OperationalError

logger = logging.getLogger(__name__)


class FAFDatabase:
    def __init__(self, loop):
        self._loop = loop
        self.engine = None

    async def connect(
        self,
        host="localhost",
        port=3306,
        user="root",
        password="",
        db="faf_test",
        minsize=1,
        maxsize=1
    ):
        if self.engine is not None:
            raise ValueError("DB is already connected!")
        self.engine = await create_engine(
            host=host,
            port=port,
            user=user,
            password=password,
            db=db,
            autocommit=True,
            loop=self._loop,
            minsize=minsize,
            maxsize=maxsize,
        )

    def acquire(self):
        return self.engine.acquire()

    async def close(self):
        if self.engine is None:
            return

        self.engine.close()
        await self.engine.wait_closed()
        self.engine = None


async def deadlock_retry_execute(conn, *args, max_attempts=3):
    for attempt in range(max_attempts - 1):
        try:
            return await conn.execute(*args)
        except OperationalError as e:
            if any(msg in e.message for msg in (
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
    return await conn.execute(*args)
