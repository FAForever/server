import asyncio
import aiomysql
from .context_cursor import ContextCursor
from aiomysql import Pool

db_pool = None

def set_pool(pool: Pool):
    """
    Set the globally used pool to the given argument
    """
    global db_pool
    db_pool = pool

@asyncio.coroutine
def connect(loop,
            host='localhost', user='root', password='', db='faf_test',
            minsize=1, maxsize=1, cursorclass=ContextCursor):
    """
    Initialize the database pool
    :param loop:
    :param host:
    :param user:
    :param password:
    :param db:
    :param minsize:
    :param maxsize:
    :param cursorclass:
    :return:
    """
    pool = yield from aiomysql.create_pool(host=host,
                                user=user,
                                password=password,
                                db=db,
                                autocommit=True,
                                loop=loop,
                                minsize=1,
                                maxsize=1,
                                cursorclass=ContextCursor)
    set_pool(pool)
    return pool
