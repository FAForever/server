#!/usr/bin/env python

from logging import handlers

from PySide.QtCore import QObject, QCoreApplication
from PySide import QtNetwork,QtSql

from passwords import DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_NAME
import config
from config import Config

#update server
from updater.updateServer import *

UNIT16 = 8

class start(QObject):

    def __init__(self, parent=None):
        try:
            super(start, self).__init__(parent)
            self.rootlogger = logging.getLogger("")
            self.logHandler = handlers.RotatingFileHandler(config.LOG_PATH + "serverUpdater.log", backupCount=15, maxBytes=524288)
            self.logFormatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s')
            self.logHandler.setFormatter(self.logFormatter)
            self.rootlogger.addHandler(self.logHandler)
            self.rootlogger.setLevel(eval("logging." + Config['serverUpdater']['loglevel']))
            self.logger = logging.getLogger(__name__)

            self.logger.info("Update server starting")
            self.db = QtSql.QSqlDatabase("QMYSQL")
            self.db.setHostName(DB_SERVER)
            self.db.setPort(DB_PORT)

            self.db.setDatabaseName(DB_NAME)
            self.db.setUserName(DB_LOGIN)
            self.db.setPassword(DB_PASSWORD)
            self.db.setConnectOptions("MYSQL_OPT_RECONNECT=1")

            if not self.db.open():
                self.logger.error(self.db.lastError().text())

            else:
                self.logger.info("DB opened.")

            self.updater = updateServer(self)
            if not self.updater.listen(QtNetwork.QHostAddress.Any, 9001):

                self.logger.error("Unable to start the server")

                return
            else:
                self.logger.info("Starting the update server on  %s:%i" % (self.updater.serverAddress().toString(),self.updater.serverPort()))
        except Exception as e:
            self.logger.exception("Error: %r" % e)

if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    import sys

    try:

        app = QCoreApplication(sys.argv)
        server = start()
        app.exec_()

    except Exception as e:

        logger.exception("Error: %r" % e)
        logger.debug("Finishing main")

