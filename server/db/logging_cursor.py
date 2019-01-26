import aiomysql

from server.decorators import with_logger


@with_logger
class LoggingCursor(aiomysql.Cursor):
    """
    Allows use of cursors using the ``with'' context manager statement.
    """
    def __init__(self, connection, echo=False):
        super().__init__(connection, echo)

    async def execute(self, query, args=None):
        clean_query = ' '.join(str(query).split())
        self._logger.debug("Executing query: %s with args: %s", clean_query, args)
        return await super().execute(query, args)

    @property
    def size(self) -> int:
        return self.rowcount
