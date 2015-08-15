import sys
import os
import logging
import hashlib
import json

from PySide.QtCore import QObject
from PySide.QtCore import QByteArray, QDataStream, QIODevice, QCoreApplication
from PySide import QtNetwork
from PySide.QtSql import *
from configobj import ConfigObj


config = ConfigObj("/etc/faforever/faforever.conf")

class updateServerThread(QObject):  # pragma: no cover
    """
    FA server thread spawned upon every incoming connection to
    prevent collisions.
    """
    
    
    def __init__(self, socketId, parent=None):
        super(updateServerThread, self).__init__(parent)

        self.log = logging.getLogger(__name__)


        self.app = None
        self.tableMod = "updates_faf"
        self.tableModFiles = "updates_faf_files"
                
        self.socket = QtNetwork.QTcpSocket(self)
        self.socket.setSocketDescriptor(socketId)
        self.parent = parent

        self.patchToCreate = []
        
        if self.socket.state() == 3 and self.socket.isValid():
            
            self.nextBlockSize = 0
    
            self.blockSize = 0   

            self.socket.readyRead.connect(self.readDatas)
            self.socket.disconnected.connect(self.disconnection)
            self.socket.error.connect(self.displayError)

            self.parent.db.open()   
              

    def getMd5(self, fileName):
        """
        Compute md5 hash of the specified file.
        IOErrors raised here are handled in doUpdate.
        """
        m = hashlib.md5()
        if not os.path.isfile(fileName): return None
        
        fd = open(fileName, "rb")
        while True:
            #read the file in 1 MiB chunks, this requires less memory in case one day we need to read something big, like textures.scd or units.scd
            content = fd.read(1024*1024) 
            if not content: break
            m.update(content)
        fd.close()
            
        return m.hexdigest()

    def updateMd5Db(self, table):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT `name` FROM %s WHERE `md5` = ''"% table)
        query.exec_()
        
        if  query.size() > 0:
            
            while query.next():
                file = str(query.value(0))
                fullPath = None
                if sys.platform == "win32":
                    fullPath = os.path.join('f:\\FAFUPDATER', table, file)
                else:
                    fullPath = os.path.join(config['global']['content_path'] + "updaterNew/", table, file)

                if os.path.exists(fullPath):
                    md5 = self.getMd5(fullPath)
                    if md5 is not None:
                        query2 = QSqlQuery(self.parent.db)
                        query2.prepare("UPDATE `faf_lobby`.`%s` SET `md5` = ? WHERE `%s`.`name` = ?;" % (table, table))
                        query2.addBindValue(md5)
                        query2.addBindValue(file)
                        query2.exec_()
                
                
    def getFileListFromDb(self, table, folder):
        files = []
        query = QSqlQuery(self.parent.db)
        query.prepare('SELECT `filename` FROM %s WHERE `path` = ?' % table)
        query.addBindValue(folder)

        query.exec_()
        if  query.size() > 0:
            while query.next():
                f = str(query.value(0))
                files.append(f)

        return files

    def getFileVersion(self, f, version, exact=False):
        query = QSqlQuery(self.parent.db)
        
        
        query.prepare("( \
select  `name` , `version`  \
from    `%s` \
LEFT JOIN `%s` ON `%s`.`id` = `%s`.`fileId` \
where    `version` >= ? and `%s`.`filename` = ?  AND obselete = 0  \
order by `version` asc \
limit 1 \
) \
union \
( \
select  `name` , `version`  \
from     `%s` \
LEFT JOIN `%s` ON `%s`.`id` = `%s`.`fileId` \
where  `version` < ? and `%s`.`filename` =  ?  AND obselete = 0  \
order by `version` desc \
limit 1 \
) \
order by abs(`version` - ?) \
limit 1   " % (self.tableModFiles, self.tableMod, self.tableMod, self.tableModFiles, self.tableMod, self.tableModFiles, self.tableMod, self.tableMod, self.tableModFiles, self.tableMod))        
        
        query.addBindValue(version)
        query.addBindValue(f)
        query.addBindValue(version)
        query.addBindValue(f)
        query.addBindValue(version)
        
        query.exec_()
        

        if  query.size() >= 1:
            query.first()  
            if exact:
                if int(query.value(1)) == int(version):
                    return str(query.value(0))
            #self.log.debug(query.value(1))
            else:
                if int(query.value(1)) > int(version):
                    return None
                else:
                    return str(query.value(0))
            return None  

    def getLatestFile(self, file):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT `name` FROM `%s` LEFT JOIN `%s` ON `%s`.`id` = `%s`.`fileId` WHERE `%s`.`filename` = ? AND obselete = 0 ORDER BY `%s`.`version` DESC" % (self.tableModFiles, self.tableMod, self.tableMod, self.tableModFiles, self.tableMod, self.tableModFiles))
        query.addBindValue(file)
        query.exec_()

        if  query.size() >= 1:
            query.first()    
            return str(query.value(0))    
        
    def handleAction(self, action, stream):
        if action == "REQUEST_SIM_PATH":
            uid = stream.readQString()
            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT filename FROM `table_mod` WHERE `uid` = ?")
            query.addBindValue(uid)
            query.exec_()
            if query.size() != 0:
                query.first()
                pathToMod = str(query.value(0))
                self.sendReply("PATH_TO_SIM_MOD", pathToMod)
            else:
                self.sendReply("SIM_MOD_NOT_FOUND")
        
        if action == "ADD_DOWNLOAD_SIM_MOD":
            uid = stream.readQString()
            query = QSqlQuery(self.parent.db)
            query.prepare("UPDATE `table_mod` SET downloads=downloads+1 WHERE uid = ?")
            query.addBindValue(uid)
            query.exec_()
                        

        
        if action == "GET_FILES_TO_UPDATE":
            
            app = stream.readQString()
            self.app = app
           
  
            if app == 'FAF':
                self.tableMod = "updates_faf"
                self.tableModFiles = "updates_faf_files"
                files = self.getFileListFromDb(self.tableMod, "bin")
                self.sendReply("LIST_FILES_TO_UP", files)


#            elif app == "balancetesting" :
#                self.tableMod = "updates_balancetesting"
#                self.tableModFiles = "updates_balancetesting_files"
#                files = self.getFileListFromDb(self.tableMod , "bin")
#                self.sendReply("LIST_FILES_TO_UP", files)
               
            elif "gamedata" in app.lower():
                files = self.getFileListFromDb(self.tableMod, "gamedata")
                self.sendReply("LIST_FILES_TO_UP", files) 
            else:
                self.tableMod = "updates_" + app
                self.tableModFiles = self.tableMod + "_files"
                files = self.getFileListFromDb(self.tableMod, "bin")
                self.sendReply("LIST_FILES_TO_UP", files)
        
        
        
        if action == "REQUEST_VERSION":
            path = stream.readQString()
            file = stream.readQString()   
            version = stream.readQString()         
           
            myFile = self.getFileVersion(file, version)
            #self.log.debug(myFile)
            if myFile is None:
                self.sendReply("UP_TO_DATE", file)
            else:
                patchFileUrl =  config['global']['content_url'] + "updaterNew/" + self.tableModFiles + "/" + myFile    
                patchFilePath =  os.path.join(config['global']['content_path'] + r"updaterNew/", self.tableModFiles, myFile)
    
               
                if os.path.isfile(patchFilePath):
                    #patchFile = QFile(patchFilePath)
                    self.sendReply("SEND_FILE_PATH", path, file, patchFileUrl)          
                else:
                    self.log.debug("File not found: " + patchFilePath) 
                    self.sendReply("ERROR_FILE", file)

        if action == "REQUEST_MOD_VERSION":
            path = stream.readQString()
            f = stream.readQString()   
            toVersions = json.loads(stream.readQString())
            version = 0         

            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT id FROM `%s` WHERE `filename` = ?" % self.tableMod)
            query.addBindValue(f)
            query.exec_()
            if query.size() != 0:
                query.first()
                fileId = str(query.value(0))
                if fileId:                    
                    if fileId in toVersions:
                        version = toVersions[fileId]

            
            fileVersion = self.getFileVersion(f, version, exact=True)
            if self.tableModFiles and fileVersion:
                patchFileUrl =  config['global']['content_url'] + "updaterNew/" + self.tableModFiles + "/" + fileVersion     
                patchFilePath =  os.path.join(config['global']['content_path'] + r"updaterNew", self.tableModFiles, fileVersion)
    
               
                if os.path.isfile(patchFilePath):

                    #patchFile = QFile(patchFilePath)
                    self.sendReply("SEND_FILE_PATH", path, f, patchFileUrl)          
                else:
                    self.log.debug("File not found: " + patchFilePath) 
                    self.sendReply("ERROR_FILE", f)    
            else:
                self.sendReply("ERROR_FILE", f)         
        if action == "REQUEST" or action == "REQUEST_PATH":
            path = stream.readQString()
            file = stream.readQString()
            ##self.log.debug("requesting file %s" % file)
            patchFileUrl =  config['global']['content_url'] + "updaterNew/" + self.tableModFiles + "/" + self.getLatestFile(file)    
            patchFilePath =  os.path.join(config['global']['content_path'] + r"updaterNew", self.tableModFiles, self.getLatestFile(file))
            
            
            if os.path.isfile(patchFilePath):

                #patchFile = QFile(patchFilePath)
                self.sendReply("SEND_FILE_PATH", path, file, patchFileUrl)          
            else: 
                self.log.debug("File not found: " + patchFilePath) 
                self.sendReply("ERROR_FILE", file)


        if action == "PATCH_TO":
            dir = stream.readQString()
            file = stream.readQString()
            md5 = stream.readQString()
            toVersion = stream.readQString()
 
            #self.log.debug(toVersion)
            #self.log.debug("got app ?")
            if self.app is not None:
                self.updateMd5Db(self.tableModFiles)
                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT `md5`, `name` FROM `%s` LEFT JOIN `%s` ON `%s`.`id` = `%s`.`fileId` WHERE `%s`.`filename` = ? AND `%s`.`version` <= ?  AND obselete = 0 ORDER BY `version` DESC" % (self.tableModFiles, self.tableMod, self.tableMod, self.tableModFiles, self.tableMod, self.tableModFiles))                
                query.addBindValue(file)
                query.addBindValue(toVersion)
                query.exec_()
                if  query.size() >= 1:
                    
                    query.first()
                    tomd5 = str(query.value(0))
                    tofilename = str(query.value(1))
                    
                    if str(md5) != str(tomd5):
                        queryStr = "SELECT patchFile FROM patchs_table WHERE fromMd5 = '%s' and toMd5 = '%s' " % (md5, tomd5)
                        query.exec_(queryStr)                       
                        if  query.size() >= 1: 
                            query.first()
                            patch = str(query.value(0))                           
                            patchFileUrl =  config['global']['content_url'] + "xdelta/" + str(patch)
                            self.sendReply("SEND_PATCH_URL", dir, file, patchFileUrl)
                        else:
                            query.prepare("SELECT `name` FROM `%s` WHERE md5 = ?" % self.tableModFiles)
                            query.addBindValue(md5)
                            query.exec_()
                            if  query.size() >= 1:
                                query.first()
                                patchfile = str(query.value(0))
                                self.log.debug("Creating patch from %s to %s " % (patchfile, tofilename))
                                patch = dict(mod=self.tableModFiles, patchfile = patchfile, tofilename = tofilename, md5 = md5, tomd5 = tomd5)
                                self.patchToCreate.append(patch)
                                #self.parent.createPatch(self.tableModFiles, str(patchfile), str(tofilename), md5, tomd5)
                                
                                self.sendReply("VERSION_PATCH_NOT_FOUND",  file)
                            else:
                                self.sendReply("VERSION_PATCH_NOT_FOUND",  file)                                                     
                    else:
                        self.sendReply("UP_TO_DATE", file)           
                else:
                    self.sendReply("VERSION_PATCH_NOT_FOUND",  file)
            else:
                self.sendReply("VERSION_PATCH_NOT_FOUND",  file) 
                        
        if action == "MOD_PATCH_TO":
            dir = stream.readQString()
            file = stream.readQString()
            md5 = stream.readQString()
            toVersions = json.loads(stream.readQString())            
            version = 0
            if not toVersions:
                self.sendReply("VERSION_MOD_PATCH_NOT_FOUND",  file)
            
            if self.app is not None:
                fileId = 0
                self.updateMd5Db(self.tableModFiles)
                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT id FROM `%s` WHERE `filename` = ?" % self.tableMod)
                query.addBindValue(file)
                query.exec_()
                if query.size() != 0:
                    query.first()
                    fileId = str(query.value(0))
                    if fileId in toVersions:
                        version = toVersions[fileId]
                        
                    
                query.prepare("SELECT `md5`, `name` FROM `%s` LEFT JOIN `%s` ON `%s`.`id` = `%s`.`fileId` WHERE `%s`.`filename` = ? AND `%s`.`version` <= ?  AND obselete = 0 ORDER BY `version` DESC" % (self.tableModFiles, self.tableMod, self.tableMod, self.tableModFiles, self.tableMod, self.tableModFiles))
                query.addBindValue(file)
                query.addBindValue(version)
                query.exec_()
                if  query.size() >= 1:
                    
                    query.first()
                    tomd5 = str(query.value(0))
                    tofilename = str(query.value(1))
                    
                    if str(md5) != str(tomd5):
                        queryStr = "SELECT patchFile FROM patchs_table WHERE fromMd5 = '%s' and toMd5 = '%s' " % (md5, tomd5)
                        query.exec_(queryStr)                       
                        if  query.size() >= 1: 
                            query.first()
                            patch = str(query.value(0))                           
                            patchFileUrl =  config['global']['content_url'] + "xdelta/" + str(patch)
                            self.sendReply("SEND_PATCH_URL", dir, file, patchFileUrl)
                        else:
                            query.prepare("SELECT `name` FROM `%s` WHERE md5 = ?" % self.tableModFiles)
                            query.addBindValue(md5)
                            query.exec_()
                            if  query.size() >= 1:
                                query.first()
                                patchfile = str(query.value(0))
                                self.log.debug("Creating patch from %s to %s " % (patchfile, tofilename))
                                patch = dict(mod=self.tableModFiles, patchfile = patchfile, tofilename = tofilename, md5 = md5, tomd5 = tomd5)
                                self.patchToCreate.append(patch)

                                #self.parent.createPatch(self.tableModFiles, str(patchfile), str(tofilename), md5, tomd5)
                                self.sendReply("VERSION_MOD_PATCH_NOT_FOUND",  file)
                            else:
                                self.sendReply("VERSION_MOD_PATCH_NOT_FOUND",  file)                                                     
                    else:
                        self.sendReply("UP_TO_DATE", file)           
                else:
                    self.sendReply("VERSION_MOD_PATCH_NOT_FOUND",  file)
            else:
                self.sendReply("VERSION_MOD_PATCH_NOT_FOUND",  file)
                                   
                                   
                                   
        if action == "UPDATE" or action == "UPDATE_PATH":
            dir = stream.readQString()
            file = stream.readQString()
            md5 = stream.readQString()

            if self.app is not None:
                
                self.updateMd5Db(self.tableModFiles)
                
                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT `md5`, `name` FROM `%s` LEFT JOIN `%s` ON `%s`.`id` = `%s`.`fileId` WHERE `%s`.`filename` = ?  AND obselete = 0 ORDER BY `%s`.`version` DESC" % (self.tableModFiles, self.tableMod, self.tableMod, self.tableModFiles, self.tableMod, self.tableModFiles))
                query.addBindValue(file)
                query.exec_()

                if  query.size() >= 1:
                    query.first()
                    latestMd5 = str(query.value(0))
                    latestName = str(query.value(1))
                    if str(md5) != str(latestMd5):
                        queryStr = "SELECT patchFile FROM patchs_table WHERE fromMd5 = '%s' and toMd5 = '%s' " % (md5, latestMd5)
                        query.exec_(queryStr)
                        
                        if  query.size() >= 1: 
                            query.first()
                            patch = str(query.value(0))                           
                            patchFileUrl =  config['global']['content_url'] + "xdelta/" + str(patch)
                            self.sendReply("SEND_PATCH_URL", dir, file, patchFileUrl)
                        else:
                            query.prepare("SELECT `name` FROM `%s` WHERE md5 = ?" % self.tableModFiles)
                            query.addBindValue(md5)
                            query.exec_()
                            #self.log.debug("query_patch " + query.executedQuery() + " " + md5)
                            if  query.size() >= 1:
                                #self.log.debug("yeps")
                                query.first()
                                patchfile = str(query.value(0))
                                patch = dict(mod= self.tableModFiles, patchfile = patchfile, tofilename = latestName, md5 = md5, tomd5 = latestMd5)
                                self.patchToCreate.append(patch)

                                #self.parent.createPatch(self.tableModFiles, str(patchfile), str(latestName), md5, latestMd5)
    
                                self.sendReply("PATCH_NOT_FOUND",  file)
                            else:
                                self.sendReply("PATCH_NOT_FOUND",  file)
                    else:
                        self.sendReply("UP_TO_DATE", file)           
                else:
                    self.sendReply("PATCH_NOT_FOUND",  file)

            else:
                self.sendReply("PATCH_NOT_FOUND",  file)


        return 1



    def readDatas(self):
        if self.socket is not None:
            if self.socket.isValid():
                ins = QDataStream(self.socket)
                ins.setVersion(QDataStream.Qt_4_2)
                loop = 0
                while not ins.atEnd():
                    QCoreApplication.processEvents()
                    loop += 1
                    if loop > 1000: break
                    if self.socket is not None:
                        if self.socket.isValid():
                            if self.blockSize == 0:
                                if self.socket.isValid():
                                    if self.socket.bytesAvailable() < 4:
                                        return
                                    self.blockSize = ins.readUInt32()
                                else:
                                    return
                            if self.socket.isValid():
                                if self.socket.bytesAvailable() < self.blockSize:
                                    bytesReceived = str(self.socket.bytesAvailable())
                                    return
                                bytesReceived = str(self.socket.bytesAvailable())
                            else:
                                return
                            action = ins.readQString()
                            self.handleAction(action, ins)
                            self.blockSize = 0
                        else:
                            return
                    else:
                        return
                return

    def disconnection(self):
        #self.log.info('client disconnect')
        self.done()

    def sendReply(self, action, *args, **kwargs):
        
        try:
            
            if hasattr(self, "socket"):

                reply = QByteArray()
                stream = QDataStream(reply, QIODevice.WriteOnly)
                stream.setVersion(QDataStream.Qt_4_2)
                stream.writeUInt32(0)
                
                stream.writeQString(action)

    
                for arg in args:
                    if isinstance(arg, int):
                        stream.writeInt(int(arg))
                    elif isinstance(arg, str):                       
                        stream.writeQString(arg) 
                    elif isinstance(arg, list):
                        stream.writeQString(str(arg))                        

                #stream << action << options
                stream.device().seek(0)
                
                stream.writeUInt32(reply.size() - 4)

                
                self.socket.write(reply)



#            else :
#                # no socket !?
#                self.quit()

        except:
                self.log.exception("Something awful happened when sending reply !")  
  
    def done(self):
        if self.socket is not None:
            #self.parent.addSocketToDelete(self.socket)
            self.socket.readyRead.disconnect(self.readDatas)
            self.socket.disconnected.disconnect(self.disconnection)
            self.socket.error.disconnect(self.displayError)
            self.socket.close()
            #self.socket.deleteLater()
            self.socket = None
        
        if len(self.patchToCreate) > 0:
            self.parent.createPatch(self.patchToCreate)


        self.parent.removeUpdater(self)
        
        
        
    # Display errors from servers
    def displayError(self, socketError):
        pass
