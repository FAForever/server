import aiomysql
import asyncio

class ContextCursor(aiomysql.Cursor):
    """
    Allows use of cursors using the ``with'' context manager statement.
    """
    def __init__(self, connection, echo=False):
        super().__init__(connection, echo)
        self.loop = asyncio.get_event_loop()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        asyncio.async(self.close())

    @property
    def size(self):
        return self.rowcount
