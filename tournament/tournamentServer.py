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

from PySide import QtCore, QtNetwork
from PySide.QtSql import *

from . import tournamentServerThread
from passwords import CHALLONGE_KEY, CHALLONGE_USER
import challonge

challonge.set_credentials(CHALLONGE_USER, CHALLONGE_KEY)



class tournamentServer(QtNetwork.QTcpServer):
    def __init__(self, parent=None):
        super(tournamentServer, self).__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.parent = parent
        self.threads    = []
        self.updaters   = []
        self.db = self.parent.db

        self.tournaments = {}
        self.importTournaments()
        
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.start(60000 * 5)
        self.updateTimer.timeout.connect(self.importTournaments) 
        
    def importTournaments(self):
        self.tournaments = {}
        ToClose = []
        for t in challonge.tournaments.index():
                uid = t["id"]
                self.tournaments[uid] = {}
                self.tournaments[uid]["name"]           = t["name"]
                self.tournaments[uid]["url"]            = t["full-challonge-url"] 
                self.tournaments[uid]["description"]    = t["description"]
                self.tournaments[uid]["type"]           = t["tournament-type"]
                self.tournaments[uid]["progress"]       = t["progress-meter"]
                self.tournaments[uid]["state"]          = "open"
                checkParticipants = False
                
                if t["started-at"] != None :
                    self.tournaments[uid]["state"]      = "started"
                    if t["progress-meter"] == 0:
                        checkParticipants = True
                if t["completed-at"] != None :
                    self.tournaments[uid]["state"]      = "finished"
                
                if t["open-signup"] == True:
                    ToClose.append(uid)
                    
                
                self.tournaments[uid]["participants"] = []


                if checkParticipants == True:
                    changed = []
                    for p in challonge.participants.index(uid) :
                        fafuid = None
                        query = QSqlQuery(self.db)
                        query.prepare("SELECT id FROM login WHERE login = ?")
                        query.addBindValue(p["name"])
                        if query.exec_():
                            if query.size() == 1 :
                                query.first()
                                fafuid = int(query.value(0))
                        if fafuid == None:
                            query.prepare("SELECT user_id FROM name_history WHERE previous_name LIKE ?")
                            query.addBindValue(p["name"])
                            if query.exec_():
                                if query.size() == 1 :
                                    query.first() 
                                    fafuid = int(query.value(0))
                            
                            self.logger.debug("player %s was not found", name)
                            query.prepare("SELECT login FROM login WHERE id =  ?")
                            query.addBindValue(fafuid)
                            if query.exec_():
                                if query.size() == 1 :
                                    query.first() 
                                    name = query.value(0)
                                    self.logger.debug("player is replaced by %s", name)
                                    challonge.participants.update(uid, p["id"], name=str(name))                                    


                        if fafuid:
                            query.prepare("SELECT session FROM login WHERE id = ?")
                            query.addBindValue(fafuid)
                            if query.exec_():
                                if query.size() == 1 :
                                    query.first()                        
                                    if int(query.value(0)) == 0:
                                        changed.append(p["id"])
                                    else:
                                        participant = {}
                                        participant["id"]   = p["id"]
                                        participant["name"] = p["name"]
                                        self.tournaments[uid]["participants"].append(participant)
                        else:
                            changed.append(p["id"])                            


                    if len(changed) != 0:
                        for puid in changed:
                            challonge.participants.destroy(uid, puid)
 
   
                else:
                    for p in challonge.participants.index(uid) :
                        fafuid = None
                        name = p["name"]
                        query = QSqlQuery(self.db)
                        query.prepare("SELECT id FROM login WHERE login = ?")
                        query.addBindValue(p["name"])
                        if query.exec_():
                            if query.size() == 1 :
                                query.first()
                                fafuid = int(query.value(0))
                        
                        if fafuid == None:
                            query.prepare("SELECT user_id FROM name_history WHERE previous_name LIKE ?")
                            query.addBindValue(p["name"])
                            if query.exec_():
                                if query.size() == 1 :
                                    query.first() 
                                    fafuid = int(query.value(0))

                            self.logger.debug("player %s was not found", name)
                            query.prepare("SELECT login FROM login WHERE id = ?")
                            query.addBindValue(fafuid)
                            if query.exec_():
                                if query.size() == 1 :
                                    query.first() 
                                    name = query.value(0)
                                    self.logger.debug("player is replaced by %s", name)
                                    challonge.participants.update(uid, p["id"], name=str(name))


                        participant = {}
                        participant["id"]   = p["id"]
                        participant["name"] = name
                        self.tournaments[uid]["participants"].append(participant)
            
                # if self.tournaments[uid]["state"] == "started":
                #     for conn in self.updaters:
                #         conn.sendJSON(dict(command="tournaments_info", data=self.tournaments))
     
        if len(ToClose) != 0:
            for uid in ToClose:
                challonge.tournaments.update(uid, open_signup="false")
                
    def incomingConnection(self, socketId):
        
        reload(tournamentServerThread)
        #self.logger.debug("Incoming tourney Connection")
        self.updaters.append(tournamentServerThread.tournamentServerThread(socketId, self))    
    

        
    def removeUpdater(self, updater):
        if updater in self.updaters:
            self.updaters.remove(updater)
            updater.deleteLater()
    
