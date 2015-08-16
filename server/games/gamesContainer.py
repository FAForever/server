import asyncio
import server.db as db
from server.decorators import with_logger

@with_logger
class GamesContainer(object):
    """Class for containing games"""
    listable = True

    def __init__(self, name, desc, nice_name, games_service=None):
        self.games = []

        self.type = 0

        self.desc = desc

        self.game_mode = name
        self.gameNiceName = nice_name
        self.parent = games_service

        self.options = []

        self._logger.debug("Initialized {}".format(nice_name))

    @asyncio.coroutine
    def getGamemodVersion(self):
        tableMod = "updates_" + self.game_mode
        tableModFiles = tableMod + "_files"
        value = {}
        with (yield from db.db_pool) as conn:
            with (yield from conn.cursor()) as cursor:
                cursor.execute("SELECT fileId, MAX(version) "
                               "FROM `%s` LEFT JOIN %s ON `fileId` = %s.id "
                               "GROUP BY fileId", (tableModFiles, tableMod, tableMod))
                rows = yield from cursor.fetchall()
                for fileId, version in rows:
                    value[fileId] = version
        return value

    def findGameById(self, id):
        """Find a game by the id"""
        for game in self.games:
            if game.id == id:
                return game
        return None

    def addGame(self, game):
        """Add a game to the list"""
        if not game in self.games:
            self.games.append(game)

