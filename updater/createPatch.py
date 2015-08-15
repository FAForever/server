import logging
import os

from PySide.QtCore import QThread, QProcess
from PySide import QtSql
from PySide.QtSql import *
from configobj import ConfigObj


config = ConfigObj("/etc/faforever/faforever.conf")

class Process(QProcess):  # pragma: no cover
    def __init__(self, patch=None, *args, **kwargs):        
        QProcess.__init__(self, *args, **kwargs)
        self.patch = None


class createPatch(QThread):  # pragma: no cover
    def __init__(self, patches, db, parent=None):
        QThread.__init__(self, parent)
        
        self.logger = logging.getLogger(__name__)
        self.process = None
        self.patches = patches
        self.parentDb = db
        self.db = None

        
    def run(self):
 
        self.logger.debug("patcher started")
        for patch in self.patches:
            mod = patch["mod"]
            fromFile = patch["patchfile"]
            toFile = patch["tofilename"]
            frommd5 = patch["md5"]
            tomd5 = patch["tomd5"]

            curPatchGen = "%s-%s.xdelta" % (fromFile, toFile)

            self.logger.debug(curPatchGen)

            self.logger.debug("opening database")
            self.db = QtSql.QSqlDatabase.cloneDatabase(self.parentDb, curPatchGen)
            source = os.path.join(config['global']['content_path'] + r"updaterNew/", mod, fromFile)
            target = os.path.join(config['global']['content_path'] + r"updaterNew/", mod, toFile)
        
            self.logger.debug(source)
            self.logger.debug(target)

            patchdest = os.path.join(config['global']['content_path'] + r"xdelta/", curPatchGen)
            self.logger.debug(patchdest)            
            
            if os.path.exists(source) and os.path.exists(target): 
                        
                executable = "python"
                arguments = [config['global']['install_path'] + "patcher.py", source, target, patchdest]
                
                self.logger.debug(arguments)
                process = QProcess()
                
                
                process.start(executable, arguments)

                if not process.waitForFinished(28800000):
                    return
                
                self.db.open()
                query = QSqlQuery(self.db)
                queryStr = "INSERT INTO patchs_table (fromMd5, toMd5, patchFile) VALUES ('%s','%s','%s')" % (frommd5, tomd5, curPatchGen)
                query.exec_(queryStr)
    #        
                self.db.close()

        #self.done() 

    def done(self):
        try:
            conn = self.db.connectionName()
            self.db.close()
            del self.db
            QtSql.QSqlDatabase.removeDatabase(conn)        
            self.deleteLater()
        except:
            pass
