from PySide import QtSql
from server.decorators import with_logger


@with_logger
class GamesContainer(object):
    """Class for containing games"""
    listable = True

    def __init__(self, name, desc, nice_name, db, games_service=None):
        self.games = []

        self.type = 0

        self.desc = desc

        self.game_mode = name
        self.gameNiceName = nice_name
        self.parent = games_service

        self.options = []

        self.db = db
        self._logger.debug("Initialized {}".format(nice_name))

    def getGamemodVersion(self):
        tableMod = "updates_" + self.game_mode
        tableModFiles = tableMod + "_files"
        value = {}
        query = QtSql.QSqlQuery(self.db)
        query.prepare("SELECT fileId, MAX(version) FROM `%s` LEFT JOIN %s ON `fileId` = %s.id GROUP BY fileId" % (tableModFiles, tableMod, tableMod))
        query.exec_()
        if query.size() != 0:
            while query.next():
                value[int(query.value(0))] = int(query.value(1)) 
        
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

