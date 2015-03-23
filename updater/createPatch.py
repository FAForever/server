#-------------------------------------------------------------------------------
# Copyright (c) 2014 Gael Honorez.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#-------------------------------------------------------------------------------

import logging
import os

from PySide.QtCore import QThread, QProcess
from PySide import QtSql
from PySide.QtSql import *
from configobj import ConfigObj


config = ConfigObj("/etc/faforever/faforever.conf")

class Process(QProcess):    
    def __init__(self, patch=None, *args, **kwargs):        
        QProcess.__init__(self, *args, **kwargs)
        self.patch = None


class createPatch(QThread):
    def __init__(self, patches, db, parent=None):
        QThread.__init__(self, parent)
        
        self.logger = logging.getLogger(__name__)
        self.process = None
        self.patches = patches
        self.parentDb = db

        
    def run(self) :
 
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
            
            if os.path.exists(source) and os.path.exists(target) : 
                        
                executable = "python"
                arguments = [config['global']['install_path'] + "patcher.py", source, target, patchdest]
                
                self.logger.debug(arguments)
                process = QProcess()
                
                
                process.start(executable, arguments)

                if not process.waitForFinished(28800000) :
                    return
                
                self.db.open()
                query = QSqlQuery(self.db)
                queryStr = "INSERT INTO patchs_table (fromMd5, toMd5, patchFile) VALUES ('%s','%s','%s')" % (frommd5, tomd5, curPatchGen)
                query.exec_(queryStr)
    #        
                self.db.close()

        #self.done() 

    def done(self):
        try :
            conn = self.db.connectionName()
            self.db.close()
            del self.db
            QtSql.QSqlDatabase.removeDatabase(conn)        
            self.deleteLater()
        except :
            pass
