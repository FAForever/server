import logging
from logging import handlers

class logger(object):
    def __init__(self):
        self.logHandler = handlers.RotatingFileHandler("gwserver.log", backupCount=15, maxBytes=524288)
        self.logFormatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s')
        self.logHandler.setFormatter( self.logFormatter )  
        
        self.logger = logging.getLogger('server.logging')
        
        self.logger.addHandler( self.logHandler )
        self.logger.setLevel( logging.DEBUG )
        self.logger.propagate = True
        
        self.logger.debug("Start logger")
        
        
    def getHandler(self):
        return self.logHandler