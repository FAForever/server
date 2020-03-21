
from server.db import FAFDatabase
from server.decorators import with_logger

@with_logger
class RatingService:
    """
    Service responsible for calculating and saving trueskill rating updates.
    To avoid race conditions, rating updates from a single game ought to be
    atomic.
    """
    def __init__(self, database: FAFDatabase):
        self._db = database

    def shutdown(self):
        """
        Finish rating all remaining games, then exit.
        """
        pass
