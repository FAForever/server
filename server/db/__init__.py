import aiomysql
from .logging_cursor import LoggingCursor
from aiomysql import Pool
from aiomysql.sa import create_engine
from . import models

db_pool = None
engine = None


def set_pool(pool: Pool):
    """
    Set the globally used pool to the given argument
    """
    global db_pool
    db_pool = pool


def set_engine(engine_):
    """
    Set the globally used engine to the given argument
    """
    global engine
    engine = engine_


async def connect(
    loop,
    host='localhost', port=3306, user='root', password='', db='faf_test',
    minsize=1, maxsize=1, cursorclass=LoggingCursor
) -> Pool:
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


async def connect_engine(loop, host='localhost', port=3306, user='root',
                         password='', db='faf_test'):
    engine = await create_engine(
        user=user,
        db=db,
        host=host,
        password=password,
        loop=loop
    )

    set_engine(engine)
    return engine
