import logging

from PySide import QtNetwork
from PySide.QtSql import *


UNIT16 = 8

from . import replayServerThread


class replayServer(QtNetwork.QTcpServer):  # pragma: no cover
    def __init__(self, parent=None):
        super(replayServer, self).__init__(parent)
        self.logger = logging.getLogger(__name__)

        self.parent = parent
        self.db = self.parent.db
        self.replayVault = []

        self.mods = {}
        self.getMods()
        
    def getMods(self):
        query = QSqlQuery(self.parent.db)
        query.setForwardOnly(True)
        query.prepare("SELECT id, gamemod FROM `game_featuredMods` WHERE 1")
        query.exec_()
        if query.size() != 0: 
            while query.next():
                uid = int(query.value(0))
                name = str(query.value(1))
                if not uid in self.mods:
                    self.mods[uid] = name       

    def incomingConnection(self, socketId):
        self.logger.debug("Incoming replay Connection")
        self.replayVault.append(replayServerThread.replayServerThread(socketId, self))    
    
    def removeUpdater(self, updater):
        if updater in self.replayVault:
            self.replayVault.remove(updater)
            updater.deleteLater()    
