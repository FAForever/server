import logging

from PySide.QtCore import SIGNAL, SLOT
from PySide import QtNetwork

from . import updateServerThread
from . import createPatch


class updateServer(QtNetwork.QTcpServer):  # pragma: no cover
    def __init__(self, parent=None):
        super(updateServer, self).__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.parent = parent
        self.threads = []
        self.db = self.parent.db
        self.updaters = []
        self.patching = False


        
    def incomingConnection(self, socketId):
        
        self.updaters.append(updateServerThread.updateServerThread(socketId, self))    

    def createPatch(self, patches):

        if not self.patching:
            self.patching = True
            self.logger.debug(patches)
            thread = createPatch.createPatch(patches, self.db)

            self.connect(thread, SIGNAL("finished()"),thread, SLOT("deleteLater()"))
            
            thread.finished.connect(self.done)     
            thread.start()
            self.threads.append(thread)
            self.logger.debug("starting patch creation")
  

        
    def removeUpdater(self, updater):
        if updater in self.updaters:
            self.updaters.remove(updater)
            updater.deleteLater()
        
        
    def done(self):
        self.logger.debug("thread done")
        
        for thread in self.threads:
            if thread:
                self.threads.remove(thread)
                try:
                    if not thread.isRunning():
                        thread.done()
                        if thread.isFinished():
                            self.patching = False
                            del thread
                except:
                    pass
