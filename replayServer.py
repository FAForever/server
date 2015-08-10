#!/usr/bin/env python3

from logging import handlers

from PySide.QtCore import QObject, QCoreApplication
from PySide import QtSql, QtNetwork
from configobj import ConfigObj

from passwords import DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_TABLE
config = ConfigObj("/etc/faforever/faforever.conf")


from replays.replayServer import *

UNIT16 = 8

class start(QObject):

    def __init__(self, parent=None):

        super(start, self).__init__(parent)

        self.rootlogger = logging.getLogger("")
        self.logHandler = handlers.RotatingFileHandler(config['global']['logpath'] + "replayServer.log", backupCount=15, maxBytes=524288)
        self.logFormatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s')
        self.logHandler.setFormatter(self.logFormatter)
        self.rootlogger.addHandler(self.logHandler)
        self.rootlogger.setLevel(eval("logging." + config['replayServer']['loglevel']))
        self.logger = logging.getLogger(__name__)


        self.db= QtSql.QSqlDatabase.addDatabase("QMYSQL")  
        self.db.setHostName(DB_SERVER)  
        self.db.setPort(DB_PORT)

        self.db.setDatabaseName(DB_TABLE)  
        self.db.setUserName(DB_LOGIN)  
        self.db.setPassword(DB_PASSWORD)
        

        if not self.db.open():  
            self.logger.error(self.db.lastError().text())  
 
        self.updater =  replayServer(self)
        if not self.updater.listen(QtNetwork.QHostAddress.Any, 11002):
            return
        else:
            self.logger.info("starting the replay server on  %s:%i" % (self.updater.serverAddress().toString(),self.updater.serverPort()))  


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)-15s %(message)s')
    logger = logging.getLogger(__name__)
    import sys
    

    try:
        app = QCoreApplication(sys.argv)
        server = start()
        app.exec_()
    
    except Exception as ex:
        
        logger.exception("Something awful happened!")
        logger.debug("Finishing main")

