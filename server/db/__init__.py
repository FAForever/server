from .context_cursor import ContextCursor
from aiomysql import Pool

db_pool = None

def set_pool(pool: Pool):
    global db_pool
    db_pool = pool
