import aiomysql
from .logging_cursor import LoggingCursor
from aiomysql import Pool

db_pool: Pool = None


def set_pool(pool: Pool):
    """
    Set the globally used pool to the given argument
    """
    global db_pool
    db_pool = pool


async def connect(loop,
                  host='localhost', port=3306, user='root', password='', db='faf_test',
                  minsize=1, maxsize=1, cursorclass=LoggingCursor) -> Pool:
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
    pool = await aiomysql.create_pool(host=host,
                                      port=port,
                                      user=user,
                                      password=password,
                                      db=db,
                                      autocommit=True,
                                      loop=loop,
                                      minsize=minsize,
                                      maxsize=maxsize,
                                      cursorclass=cursorclass)
    set_pool(pool)
    return pool
