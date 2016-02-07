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
        self._logger.debug("Executing query: {} with args: {}".format(query, args))
        return await super().execute(query, args)

    @property
    def size(self):
        return self.rowcount
