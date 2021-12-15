import asyncio

from server.db import FAFDatabase


class MockConnectionContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        await self._db._lock.acquire()
        return self._db._connection

    async def __aexit__(self, exc_type, exc, tb):
        self._db._lock.release()


class MockDatabase(FAFDatabase):
    """
    This class mocks the FAFDatabase class, rolling back all transactions
    performed during tests. To do that, it proxies the real db engine, giving
    access to a single connection the results of which are never comitted.
    Since the server uses that single connection, it sees all changes made, but
    at the same time we can rollback all these changes once the test is over.

    Note that right now the server relies on autocommit behaviour sqlalchemy.
    Any future manual commit() calls should be mocked here as well.
    """
    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        db: str = "faf_test",
        **kwargs
    ):
        super().__init__(host, port, user, password, db, **kwargs)
        self._connection = None
        self._conn_present = asyncio.Event()
        self._lock = asyncio.Lock()
        self._done = asyncio.Event()
        self._keep = asyncio.create_task(self._keep_connection())

    async def connect(self):
        await self._conn_present.wait()

    async def _keep_connection(self):
        async with self.engine.begin() as conn:
            self._connection = conn
            self._conn_present.set()
            await self._done.wait()
            await conn.rollback()
            self._connection = None

    def acquire(self):
        return MockConnectionContext(self)

    async def close(self):
        async with self._lock:
            self._done.set()
            await self._keep
            await self.engine.dispose()
