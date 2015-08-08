import aiomysql
import asyncio

db_pool = None


def init_db_pool(pool: aiomysql.Pool):
    global db_pool
    db_pool = pool


class CursorContext(aiomysql.Cursor):
    def __exit__(self, exc_type, exc_val, exc_tb):


@asyncio.coroutine
def cursor():
    return CursorContext()
