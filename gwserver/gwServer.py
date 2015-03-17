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
import json
import os
import time
import hashlib
import math
import base64

from PySide import QtCore, QtNetwork
from PySide.QtSql import QSqlQuery

from . import lobby
from . import attacks
from . import defenses
from . import newsFeed
from . import teams
from . import domination
from . import depots
from . import phpserialize


ATTACK_PERDIOD = 1 * 60 * 60 # 1 hour
ATTACK_WIN_RATIO = 0.05
ATTACK_THRESHOLD = 0.5
WIN_PAID = 100

from configobj import ConfigObj
config = ConfigObj("/etc/faforever/faforever.conf")

TEXPATH = config['global']['content_path'] + "/images"

FACTIONS = {0:"uef", 1:"aeon", 2:"cybran", 3:"seraphim"}
CONTROL_THRESHOLD = 0.9


class gwServer(QtNetwork.QTcpServer):
    def __init__(self, db, parent=None):
        super(gwServer, self).__init__(parent)
        
        self.log = logging.getLogger(__name__)
        
        self.log.info("initialize server dispatcher")

        self.planets    = {}
        self.links      = {}

        self.factionPlayers = {}
        for i in range(4) :
            self.factionPlayers[i] = {}
            for j in range(8) :
                self.factionPlayers[i][j] = []
                

        
        self.attackTimer = QtCore.QTimer(self)
        self.attackTimer.timeout.connect(self.attacksCheck)
        self.attackTimer.start(10000)
        
        self.defendersOnHold    = {}
        self.attackOnHold       = {}
        #self.attackersAsked     = {}
        
        self.parent = parent

        self.attackWaitTimer = QtCore.QTimer(self)
        self.attackWaitTimer.timeout.connect(self.attacksWaitCheck)
        self.attackWaitTimer.start(5000)

        self.influenceCheckTimer = QtCore.QTimer()
        self.influenceCheckTimer.timeout.connect(self.influenceCheck)
        self.influenceCheckTimer.start(300000)


        self.db = db
        self.recorders = []

        self.attacks            = attacks.Attacks(self)
        self.teams              = teams.Teams(self)
        self.newsFeed           = newsFeed.NewsFeed(self)
        self.domination         = domination.Domination(self)
        self.planetaryDefenses  = defenses.Defenses(self)
        self.depots             = depots.Depots(self)
        
        self.massFactors = self.getMassFactors()



    def getMassFactors(self):
        massCosts = {}
        for faction in range(4):
            massCosts[faction] = []
            for tech in range(1,4):
                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT blueprint FROM faf_unitsDB.vvjnxsdj89235d WHERE category = 'Vehicle' and LOWER(faction) = ? and tech_level = ?")
                query.addBindValue(FACTIONS[faction])
                query.addBindValue(tech)        
                query.exec_()        
                
                numberUnits = query.size()
                totalMass = 0
                if numberUnits > 0:
                    while next(query):
                        blueprint = base64.b64decode(str(query.value(0)))
                        bpdecoded = phpserialize.loads(blueprint)
                        totalMass = totalMass + int(bpdecoded["UnitBlueprint"]["Economy"]["BuildCostMass"])
                    
                finalCost = float(totalMass)/float(numberUnits)
                self.log.debug("%s tech %i : %f" % (FACTIONS[faction], tech, finalCost))
                massCosts[faction].append(finalCost)
                
        return massCosts
                

    def getMd5(self, fileName):
        '''
        Compute md5 hash of the specified file.
        '''
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

    def autorecall(self, message):
        uid = message["playeruid"]
        curramount = 0
        query = QSqlQuery(self.db)
        query.prepare("SELECT `amount` FROM `item_bought` WHERE `useruid` = ? and itemuid = 0")
        query.addBindValue(uid)
        if query.exec_():
            if query.size() >0:
                query.first()      
                curramount = int(query.value(0))
        
        query = QSqlQuery(self.db)
        query.prepare("UPDATE `item_bought` set `amount` = `amount`-1 where `useruid` = ? and itemuid = 0")
        query.addBindValue(uid)
        if query.exec_():
            for conn in self.recorders :
                if conn.uid == uid:
                    item = dict(command="group_reinforcements_info", group=0, unit=0, amount = curramount-1)
                    conn.sendJSON(item)        
                    return                 

    def sendAttackToAll(self):
        self.log.debug("sending attack update to all players")
        try :
            for conn in self.recorders :
                conn.sendAttacks(False)
        except :
            self.log.exception("Something awful happened while sending an attack result to all !")

    def playerAttackCheck(self, message):
        planetuid   = message["planet"]
        defenders   = message["defenders"]
        attackers   = message["attackers"]
        self.log.debug("attack check : %s", planetuid)
        self.log.debug(defenders)
        self.log.debug(attackers)
        
        canAttack           = True

        for uid in defenders :
            if uid != 'null' :
                if defenders[uid] == False :
                    canAttack = False
                    # some defenders are offline or in game.
                    if len(defenders) > 1 :
                        for uidDefender in defenders :
                            if defenders[uidDefender] != False :
                                self.setConnState(uidDefender, False)
                                for conn in self.recorders :
                                    if conn.uid == int(uidDefender) :
                                        self.log.info("uid defender %i not available" % int(uidDefender) )
                                        if not self.sendToConn(uid, dict(command="searching", state="off")) :
                                            self.log.error("Unable to find player %i", int(uidDefender))
                                        conn.sendJSON(dict(command="notice", style="info", text="Some of your team mates are offline or in game."))
                                        
                                        break
                    
                    
            else :
                self.log.error("uid defender not found")
                return

        if canAttack == False:
            self.log.debug("some attackers are not there.")
            if planetuid in self.defendersOnHold :
                del self.defendersOnHold[planetuid]       
    
            for uid in self.attacks.getTeamUids(planetuid, 1):
                self.setConnState(uid, False)
            for uid in self.attacks.getTeamUids(planetuid, 2):
                self.setConnState(uid, False)                
            
            if self.attacks.isMutualAttack(planetuid):
                self.log.debug("Attack was mutual, defense not here, attack wins - it continue.")
                #TODO: PAY PLAYER
                self.registerGameResult(planetuid, True)
            self.gameClean(planetuid)
            return
            
            
        
        self.log.debug("checking attackers")

        for uid in attackers :
            if uid != "null" :
                uid_int = int(uid)
                if attackers[uid] == False or self.getConnState(uid_int) == False :
                    self.log.debug("Can't attack : %i is not here" % uid_int)
                    self.log.debug(self.getConnState(uid_int))
                    self.log.debug(attackers[uid])
                    canAttack = False
                    #some attackers are not there.
            else :
                canAttack = False

        if canAttack :
            #last check
            self.attacks.setLaunching(planetuid)
            self.launchGame(planetuid)
            #self.parent.send(dict(command="launch_game", planet=planetuid, faction_defenders = faction_defenders, faction_attackers = faction_attackers, defenders=defenders, attackers=attackers))

        else :
            for uid in self.attacks.getTeamUids(planetuid, 2):
                self.log.debug("sending search off to %i and registering victory.", uid)
                if not self.sendToConn(uid, dict(command="searching", state="off")) :
                    self.log.error("Unable to find player %i", int(uid))
                self.setConnState(uid, False)

            if planetuid in self.defendersOnHold :
                del self.defendersOnHold[planetuid]       

            self.log.debug("defense win - attack cancelled")
            self.registerGameResult(planetuid, False)
            self.updateAttackList()
            self.sendAttackToAll()

            
                    
    def attack_proposal(self, planetuid):
        # We have to go through the attacker list, starting with higher ranked players first...
        # getting the attackers faction
        pass

                    
                   
    def attackResult(self, message):
        ''' Handle a game result '''
        try :
            
            planetuid = message["planetuid"]
            self.log.debug("Handling game result for planet %i !" % planetuid)
            
            uuid = message["gameuid"]
            if uuid:
                query = QSqlQuery(self.db)
                query.prepare("UPDATE game_stats set `EndTime` = NOW() where `id` = ?")
                query.addBindValue(uuid)
                query.exec_()
                self.log.debug("uuid : %s" % str(uuid))
            else:
                self.log.error("no uuid !?")
                return

            defendFaction = self.attacks.getSecondFaction(planetuid)
            attackFaction = self.attacks.getFirstFaction(planetuid)

            if not self.attacks.exists(planetuid):
                self.log.debug("attack do not exists !?")
                return

            attackersuid = self.attacks.getTeamUids(planetuid, 1)
            defendersuid = self.attacks.getTeamUids(planetuid, 2)
            
            for uid in attackersuid :
                self.setConnState(uid, False)
            for uid in defendersuid :
                self.setConnState(uid, False)
            
            self.log.debug(message["results"])
            results = None
            try:
                results = json.loads(message["results"])
            except:
                self.log.debug("Error: empty result")


            if results != None :
            # convert the key to integer.
                for key in  list(results.keys()) :
                    results[int(key)] = results.pop(key)
                for key in  list(results[1]["players"].keys()) :
                    results[1]["players"][int(key)] = results[1]["players"].pop(key)  
        
                for key in  list(results[2]["players"].keys()) :
                    results[2]["players"][int(key)] = results[2]["players"].pop(key)
            else:
                self.log.debug("game scores are not correct")
                query = QSqlQuery(self.db)
                query.prepare("DELETE FROM `attacks` WHERE `uid_planet` = ?")
                query.addBindValue(planetuid)
                query.exec_() 
                self.updateAttackList()
                self.updateGalaxy()
                self.sendAttackToAll()
                return                

            if not "score" in results[1] or not "score" in results[2] :
                self.log.debug("game scores are not correct")
                query = QSqlQuery(self.db)
                query.prepare("DELETE FROM `attacks` WHERE `uid_planet` = ?")
                query.addBindValue(planetuid)
                query.exec_() 
                self.updateAttackList()
                self.updateGalaxy()
                self.sendAttackToAll()
                return  

            if attackFaction == None or defendFaction == None:
                self.log.warning("error with factions")
            
            ## Handling death of players...
            for uid in results[1]["players"] :
                #register scores
                if uuid:
                    avatarUid = self.getAvatarUid(uid)
                    if  avatarUid is None:
                        self.log.error("no Avatar uid ! %i" % uid)
                    else:
                        query = QSqlQuery(self.db)
                        query.prepare("UPDATE game_player_stats set `score` = ? where `gameId` = ? and `avatarId` = ?")
                        query.addBindValue(results[1]["players"][uid])
                        query.addBindValue(uuid)
                        query.addBindValue(avatarUid)
                        if not query.exec_():
                            self.log.error(query.lastError())
                
                if results[1]["players"][uid] < 0 :
                    if attackFaction != None or defendFaction != None:
                        try:
                            if results[1]["players"][uid] == -2 : 
                                self.newsFeed.playerDeath(int(uid), attackFaction, defendFaction, planetuid)
                        except:
                            pass
                    rank = self.getAvatarRank(uid)
                    if results[1]["players"][uid] == -2 :                       
                        self.playerDeath(uid)
                    # get the rank of the dying guy
                    
                    for puid in results[2]["players"]  :
                        if results[2]["players"][puid] != -2 :
                            multi = 1
                            if results[1]["players"][uid] == -2:
                                multi = 1.5
                            else:
                                multi = 1
                            self.log.debug("kill bonus")
                            self.payPlayer(puid, WIN_PAID + (rank * multi * WIN_PAID))
                    
            for uid in results[2]["players"]:
                #register scores
                if uuid:
                    avatarUid = self.getAvatarUid(uid)
                    if avatarUid is None:
                        self.log.error("no Avatar uid ! %i" % uid)
                    else:
                        query = QSqlQuery(self.db)
                        query.prepare("UPDATE game_player_stats set `score` = ? where `gameId` = ? and `avatarId` = ?")
                        query.addBindValue(results[2]["players"][uid])
                        query.addBindValue(uuid)
                        query.addBindValue(avatarUid)
                        if not query.exec_():
                            self.log.error(query.lastError())     

                if results[2]["players"][uid] < 0  :
                    if attackFaction != None or defendFaction != None:
                        if results[2]["players"][uid] == -2:
                            self.newsFeed.playerDeath(int(uid), defendFaction, attackFaction, planetuid)
                    
                    rank = self.getAvatarRank(uid)
                    if results[2]["players"][uid] == -2:
                        self.playerDeath(uid)
                    
                    for puid in results[1]["players"]  :
                        if results[1]["players"][puid] != -2 :
                            self.log.debug("kill bonus")
                            multi = 1
                            if results[2]["players"][uid] == -2:
                                multi = 1.5
                            self.payPlayer(puid, WIN_PAID + rank  * multi * WIN_PAID)
            
            
            if results[1]["score"] > results[2]["score"] :
                self.registerGameResult(planetuid, True)
            elif results[1]["score"] < results[2]["score"] :
                self.registerGameResult(planetuid, False)
            else :
                self.registerGameResult(planetuid, False)
            
            self.log.debug("update attack list")
            self.updateAttackList()
            self.log.debug("send Attack to all")
            self.sendAttackToAll()
      
        except :
            self.log.exception("Something awful happened while reporting a game result !")

    def cleanGames(self, playeruid):
        '''clean all the games launched'''
        doneSomething = False
        for planetuid in self.attacks.cleanGames(playeruid):
            self.log.debug("Player has left for planet %i" % planetuid)
            self.gameAborted(planetuid, playeruid, immediate=True)
            doneSomething = True
        return doneSomething

    def cleanAvatar(self, uid):  
        ''' remove the avatar '''
        for faction in self.factionPlayers :
            for rank in self.factionPlayers[faction] :
                if uid in self.factionPlayers[faction][rank] : 
                    self.factionPlayers[faction][rank].remove(uid)
        

    def findPlayerInfos(self, uid):
        query = QSqlQuery(self.db)
        query.prepare("SELECT rank, name FROM avatars WHERE uid = ? AND alive = 1")
        query.addBindValue(uid)
        query.exec_()         

        if query.size() > 0 :
            query.first()
            return int(query.value(0)), str(query.value(1))
        return None, None

        
        
                
    def playerDeath(self, uid):
        self.log.debug("Player %i is dead !" %uid)
        self.setConnState(uid, False)
        self.sendToConn(uid, dict(command="notice", style="info", text="Your avatar died during the war... Rest in peace."))
        
        ## remove all units
        self.removeReinforcementsUnits(uid)
        ## we remove all his attack
        query = QSqlQuery(self.db)
        query.prepare("DELETE FROM `attacks` WHERE `uid_player` = ?")
        query.addBindValue(uid)
        query.exec_()         
        self.cleanAvatar(uid)

        #self.updateAttackList()
        #self.sendAttackToAll()
        
        ## we remove the avatar
        query = QSqlQuery(self.db)
        query.prepare("UPDATE `avatars` SET `alive`=0 WHERE uid = ? and `alive` = 1")
        query.addBindValue(uid)
        if not query.exec_() :
            self.log.error(query.lastError())
                
        for conn in self.recorders :
            if conn.uid == int(uid) :
                conn.get_name()
                return            


    def playerHasJoin(self, planetuid, playeruid) :
        self.log.debug("player %i has join for planet %i" % (playeruid, planetuid))
        self.attacks.registerJoin(planetuid, playeruid)
        

    def playerHasLeft(self, planetuid, playeruid) :
        self.log.debug("player %i has left for planet %i" % (playeruid, planetuid))
        self.setConnState(playeruid, False)
        if playeruid in self.attacks.getTeamUids(planetuid, 1):
            # if the attacker has left....
            if self.attacks.isMutualAttack(planetuid):                
                # we must give the other player his money back
                for uid in self.attacks.getTeamUids(planetuid, 2):
                    self.payPlayer(uid, 100, add=False)
            
            if self.attacks.hasJoined(planetuid, playeruid) == False or self.attacks.getCancel(planetuid) > 1 :
                # the attackers can't stop cancelling, we remove his game.
                self.registerGameResult(planetuid, False)
                self.updateAttackList()
                self.sendAttackToAll()
                return
            
            self.attacks.registerCancel(planetuid)
        
        self.log.debug("resetting state - Game aborted")
        self.gameClean(planetuid)
            

    def gameClean(self, planetuid):
        self.log.debug("game clean on planet %i", planetuid)
        attackers = self.attacks.getTeamUids(planetuid, 1)
        defenders = self.attacks.getTeamUids(planetuid, 2)

        for uid in attackers :
            self.setConnState(uid, False)
        for uid in defenders :
            self.setConnState(uid, False)

        if planetuid in self.defendersOnHold :
            del self.defendersOnHold[planetuid]
        

        for uid in self.attacks.getTeamUids(planetuid, 2) :
            if not self.sendToConn(uid, dict(command="searching", state="off")):
                self.log.error("Unable to find player %i", int(uid))
            #self.sendToConn(uid, dict(command="notice", style="info", text="The game was cancelled."))
        
        for uid in self.attacks.getTeamUids(planetuid, 1) :
            if not self.sendToConn(uid, dict(command="searching", state="off")):
                self.log.error("Unable to find player %i", int(uid))
            #self.sendToConn(uid, dict(command="notice", style="info", text="The game was cancelled."))   

        self.log.debug("resetting state")
        self.attacks.removeDefenders(planetuid)
        self.attacks.setUndefended(planetuid)
        self.attacks.resetState(planetuid)
        self.updateAttackList()
        
            
            
            
    def gameAborted(self, planetuid, quitter=None, immediate = False):
        ''' game was cancelled '''
        
        if self.attacks.isDefended(planetuid) :
            self.log.debug("Defended : Can't cancel")
            return
        
        #double chieck
        query = QSqlQuery(self.db)
        query.prepare("SELECT defended FROM attacks WHERE `uid_planet` = ?")
        query.addBindValue(planetuid)
        query.exec_()
        if query.size() > 0:
            query.first()
            if int(query.value(0)) == 1:
                self.log.debug("Defended : Can't cancel")
                return
        
        # sending search off
        for uid in self.attacks.getTeamUids(planetuid, 1):
            self.sendToConn(uid, dict(command="searching", state="off"))

        for uid in self.attacks.getTeamUids(planetuid, 2):
            self.sendToConn(uid, dict(command="searching", state="off"))
        
        if self.attacks.isWaiting(planetuid) == False or immediate==True:
            self.log.debug("game cancelled on planet %i", planetuid)
            if immediate:
                self.log.debug("Was killed immediately")
            
            if self.attacks.isMutualAttack(planetuid):                
                # we must give the other player his money back
                for uid in self.attacks.getTeamUids(planetuid, 2):
                    self.payPlayer(uid, 100, add=False)
            
            if self.attacks.getCancel(planetuid) > 1 or immediate is True :
                # the attackers can't stop cancelling, we remove his game.
                self.log.debug("game cancelled too many times.")
                
                if quitter in self.attacks.getTeamUids(planetuid, 1) or quitter == None:
                    #the attacker left.
                    self.registerGameResult(planetuid, False)
                    # we cancel the attack.
                    self.cancelAttack(planetuid)
                    self.updateAttackList()
                    self.sendAttackToAll()
                    return
                else:
                    # defender left.
                    self.registerGameResult(planetuid, True)
                    self.gameClean(planetuid)
                    self.sendAttackToAll()
                    return
                    

            self.log.debug("register cancel")
            self.attacks.registerCancel(planetuid)
            
            self.gameClean(planetuid)
            self.sendAttackToAll()
            

        
    def attackStarted(self, planetuid, uuid):
        ''' set the game as started '''

        self.log.debug("attack started on planet %i" % planetuid)
        attackers = self.attacks.getTeamUids(planetuid, 1)
        defenders = self.attacks.getTeamUids(planetuid, 2)

        if len(attackers) != 0 :
            
            for uid in attackers :
                self.setConnState(uid, True)
                #self.removeReinforcementsUnits(uid)
            
            for uid in defenders :
                self.setConnState(uid, True)
                #self.removeReinforcementsUnits(uid)

            query = QSqlQuery(self.db)
            query.prepare("UPDATE `attacks` SET defended = 1 WHERE `uid_planet` = ?")

            query.addBindValue(planetuid)
            query.exec_()

            #uuid = self.attacks.getGameUid(planetuid)
            if uuid:
                query = QSqlQuery(self.db)
                query.prepare("UPDATE game_stats set `startTime` = NOW() where `id` = ?")
                query.addBindValue(uuid)
                query.exec_()
           
                for uid in attackers:
                    avatarUid = self.getAvatarUid(uid)
                    rank = self.getAvatarRank(uid)
                    if rank is None:
                        self.log.error("no rank found !? %i" % uid)
                        continue
                    query = QSqlQuery(self.db)
                    query.prepare("INSERT INTO `game_player_stats`(`gameId`, `avatarId`, `rank`) VALUES (?,?,?)")
                    query.addBindValue(uuid)
                    query.addBindValue(avatarUid)
                    query.addBindValue(rank)
                    query.exec_()
                    
                for uid in defenders:
                    avatarUid = self.getAvatarUid(uid)
                    rank = self.getAvatarRank(uid)
                    if rank is None:
                        self.log.error("no rank found !? %i" % uid)
                        continue
                    query = QSqlQuery(self.db)
                    query.prepare("INSERT INTO `game_player_stats`(`gameId`, `avatarId`, `rank`) VALUES (?,?,?)")
                    query.addBindValue(uuid)
                    query.addBindValue(avatarUid)
                    query.addBindValue(rank)
                    query.exec_()


            self.updateAttackList()
            self.sendAttackToAll()            
    
            if planetuid in self.defendersOnHold :
                del self.defendersOnHold[planetuid]
        else :
            self.log.error("attacker not found for planet %i" % planetuid)
        
        
    def removeReinforcementsUnits(self, uid):
        query = QSqlQuery(self.db)
        query.prepare("DELETE FROM `reinforcements_groups` WHERE `userId` = ?")
        query.addBindValue(uid)
        query.exec_()
        
    def delete_group(self, message):
        group   = message["group"]
        uid     = message["playeruid"]
        for conn in self.recorders :
            if conn.uid == uid:
                conn.groupDeleted(group)
                return         
    
    def removeUpgrades(self, uid):
        self.log.debug("removing items")
        avataruid = self.getAvatarUid(uid)
        if avataruid is None:
            self.log.debug("avatar not found")
            return None
        
        query = QSqlQuery(self.db)
        query.prepare("SELECT item_bought.id, amount FROM static_defenses LEFT JOIN item_bought ON static_defenses.`id` = item_bought.itemuid WHERE `avataruid`=? and temporary = 1")
        query.addBindValue(avataruid)
        if not query.exec_():
            self.log.error(query.lastError())
        if query.size() > 0:
            while next(query):
                idStruct   = int(query.value(0))
                amount      = int(query.value(1))
                self.log.debug("removing item %i from player %i" % (idStruct, uid))
                if amount == 0:
                    continue
                query2 = QSqlQuery(self.db)
                query2.prepare("UPDATE item_bought SET amount=amount-1 WHERE id = ?")
                query2.addBindValue(idStruct)
                if not query2.exec_():
                    self.log.error(query.lastError())
                self.sendUpgrades(uid)
    
    def getUpgrades(self, uid):
        avataruid = self.getAvatarUid(uid)
        if avataruid is None:
            return None
        
        avatarname = self.getAvatarName(uid)
        
        query = QSqlQuery(self.db)
        query.prepare("SELECT structure, activation, amount FROM static_defenses LEFT JOIN item_bought ON static_defenses.`id` = item_bought.itemuid WHERE `avataruid`=? and temporary = 1")
        query.addBindValue(avataruid)
        query.exec_()
        if query.size() > 0:
            playerUpgrades = []
            while next(query):
                structure   = str(query.value(0))
                activation  = int(query.value(1))
                amount      = int(query.value(2))
                if amount == 0:
                    continue
                upgrade = {}
                upgrade["playerName"]=avatarname
                upgrade["delay"] = activation
                upgrade["unitNames"] = [structure]
                playerUpgrades.append(upgrade)
                                
            return playerUpgrades
        return None
                
    def getPlanetDefenses(self, planetuid):
        defenders   = self.attacks.getTeamUids(planetuid,2)
        factionDefend  = self.attacks.getSecondFaction(planetuid)
        
        if self.attacks.isMutualAttack(planetuid):
            defenders = self.attacks.getTeamUids(planetuid,1)
            factionDefend = self.attacks.getFirstFaction(planetuid)
        
        
        if len(defenders) == 0:
            self.log.debug("no defenders !?")
            return
        
        playeruid = defenders[0]

        avataruid = self.getAvatarUid(playeruid)
        if avataruid is None:
            return None
        
        avatarname = self.getAvatarName(playeruid)
                
        query = QSqlQuery(self.db)
        query.prepare("SELECT structure, activation, amount, faction FROM static_defenses LEFT JOIN planets_defense ON static_defenses.`id` = planets_defense.itemuid WHERE `planetuid`=?")
        query.addBindValue(planetuid)
        query.exec_()
        if query.size() > 0:
            planetUpgrades = []
            while next(query):
                structure   = str(query.value(0))
                activation  = int(query.value(1))
                amount      = int(query.value(2))
                faction     = int(query.value(3))

                if faction != factionDefend :
                    if not faction in self.domination.getDominantSlaves(factionDefend):
                        continue
                if amount == 0:
                    continue
                upgrade = {}
                upgrade["playerName"]=avatarname
                upgrade["delay"] = activation
                upgrade["unitNames"] = [structure]*amount
                planetUpgrades.append(upgrade)
                                
            return planetUpgrades
        return None
            
            
    def computeTimeReinforcement(self, mass, tech, faction):
        return int((math.pow(math.log1p(tech),4.1) * (mass / self.massFactors[faction][tech-1]))*60)
            
            
    def getPassiveItems(self, playersUid):
        passiveItems = []
        for playeruid in playersUid:
            avataruid = self.getAvatarUid(playeruid)
            if avataruid is None:
                continue
            avatarname = self.getAvatarName(playeruid)

            passiveItem = {}
            
            
            query = QSqlQuery(self.db)
            query.prepare("SELECT `itemuid`,`amount` FROM `item_bought` WHERE `useruid` = ?")
            query.addBindValue(playeruid)
            query.exec_()
            if query.size() > 0:
                while next(query):
                    item = int(query.value(0))
                    amount = int(query.value(1))                        
                    if item == 0 and amount > 0:
                        passiveItem["playerName"]= avatarname
                        passiveItem["itemNames"] = ["autorecall"]

            passiveItems.append(passiveItem)
        return passiveItems
        
    def getUnitReinforcements(self, playersUid):
        reinforcements = []
        
        for playeruid in playersUid:
            
            groups = {}
            totalDelay = 0
            avataruid = self.getAvatarUid(playeruid)
            if avataruid is None:
                continue
            avatarname = self.getAvatarName(playeruid)
                        
            query = QSqlQuery(self.db)
            query.prepare("SELECT `group`,`unit`,`amount` FROM `reinforcements_groups` WHERE `userId` = ? AND `group` > 0 ORDER BY `group`")
            query.addBindValue(playeruid)
            query.exec_()
            if query.size() > 0:
                while next(query):
                    group = int(query.value(0))
                    unit = str(query.value(1))
                    amount = int(query.value(2))
                    delay = 0
                    query2 = QSqlQuery(self.parent.db)
                    query2.prepare("SELECT tech_level, blueprint, faction FROM faf_unitsDB.vvjnxsdj89235d WHERE bp_name = ?")
                    query2.addBindValue(unit)    
                    query2.exec_()
                    if query2.size()!=0:
                        query2.first()
                        tech_level = int(query2.value(0))
                        blueprint = base64.b64decode(str(query2.value(1)))
                        bpdecoded = phpserialize.loads(blueprint)
                        mass = int(bpdecoded["UnitBlueprint"]["Economy"]["BuildCostMass"])
                        factName = str(query2.value(2))
                        faction = 0
                        if factName.lower() == "uef":
                            faction = 0
                        elif factName.lower() == "aeon":
                            faction = 1
                        elif factName.lower() == "cybran":
                            faction = 2
                        elif factName.lower() == "seraphim":
                            faction = 3

                        delay = self.computeTimeReinforcement(mass, tech_level, faction) * amount
                    
                    if not group in groups:
                        groups[group] = []
                        
                    groups[group].append(dict(unit=unit, amount=amount, delay=delay))
            
            
            totalDelay = 0
            for group in groups:
                reinforcement = {}
                reinforcement["playerName"]=avatarname
                reinforcement["unitNames"] = []
                reinforcement["delay"] = 0
                items = groups[group]
                for item in items:
                    #totalDelay = totalDelay + item["delay"]
                    reinforcement["unitNames"] = reinforcement["unitNames"] + [item["unit"]]*item["amount"] 
                    reinforcement["delay"] = reinforcement["delay"] + item["delay"]
                reinforcement["group"] = group
                reinforcements.append(reinforcement)
                           
                
        return reinforcements
    
    
    def launchGame(self, planetuid):
        faction_attackers   = self.attacks.getFirstFaction(planetuid)
        faction_defenders   = self.attacks.getSecondFaction(planetuid)
        attackers           = self.attacks.getTeamUids(planetuid,1)
        defenders           = self.attacks.getTeamUids(planetuid,2)
        
        upgrades = {}
        upgrades["initialStructure"] = []
        upgrades["initialUnitWarp"] = []
        upgrades["periodicUnitWarp"] = []
        upgrades["transportedUnits"] = []
        upgrades["passiveItems"] = []
        

        #check the defense for planet.
        upgradesPlanet = self.getPlanetDefenses(planetuid)
        if upgradesPlanet is not None:
            upgrades["initialStructure"] = upgradesPlanet
            
        
        #Check for reinforcements
        unitReinforcements = self.getUnitReinforcements(attackers+defenders)
        if unitReinforcements is not None:
            upgrades["transportedUnits"] = unitReinforcements
        
        # Check for passive items
        passiveItems = self.getPassiveItems(attackers+defenders)
        if passiveItems is not None:
            upgrades["passiveItems"] = passiveItems

        self.log.debug("upgrades : " + str(upgrades))
        
        self.log.debug("Launching a game")
        
        for uid in attackers : 
            #self.sendToConn(uid, dict(command="game_upgrades", upgrades=upgrades))
            self.setConnState(uid, True)
        for uid in defenders : 
            #self.sendToConn(uid, dict(command="game_upgrades", upgrades=upgrades))
            self.setConnState(uid, True)  
        
       
        self.attacks.setReinforcements(planetuid, json.dumps(upgrades))

        self.attacks.setLaunched(planetuid)
        
        self.parent.send(dict(command="launch_game", planet=planetuid, faction_defenders = faction_defenders, faction_attackers = faction_attackers, defenders=defenders, attackers=attackers, luatable=upgrades))
        
    def tryLaunchGame(self, planetuid):
        ''' launch a game between two players'''
        # let check if everyone is still online first...
        
        if planetuid in self.defendersOnHold :
            del self.defendersOnHold[planetuid]        
        
        attackers    = self.attacks.getTeamUids(planetuid, 1) 
        defenders    = self.attacks.getTeamUids(planetuid, 2)
        self.defendersOnHold[planetuid] = defenders
        self.log.debug("get teams")
        self.log.debug(attackers)
        self.log.debug(defenders)
        ## First we delete the attack from the list, and put it in the defense list.
        self.parent.send(dict(command="attack_check", planet=planetuid, defenders=defenders, attackers=attackers))
        self.updateAttackList()
        self.sendAttackToAll()
        

    def gameInfo(self, message):
        uuid = message["uuid"]
        planetuid = message["planetuid"]
        self.log.debug("Linking game ID %s" % str(uuid))
        self.attacks.setGameUid(planetuid, uuid)
        
        reinforcements = self.attacks.getReinforcements(planetuid)
        if reinforcements != None :
            query = QSqlQuery(self.db)
            query.prepare("INSERT INTO `reinforcements_replays`(`uid`, `table`) VALUES (?,?)")
            query.addBindValue(uuid)
            query.addBindValue(reinforcements)
            if not query.exec_():
                self.log.error(query.lastError())

    def gameHosted(self, planetuid):
        ''' a game is hosted '''  
        self.attacks.setHosted(planetuid)
        for uid in self.attacks.getTeamUids(planetuid, 2) :
            if not self.sendToConn(uid, dict(command="searching", state="off")) :
                self.log.error("Unable to find player %i", int(uid))
        
    def attacksWaitCheck(self):
        ''' Handle second in command '''
        try :
            
            attackToCancel = []
            requestToDelete = []
            for planetuid in self.attackOnHold :
                timeHold = self.attackOnHold[planetuid]
                if time.time() - timeHold > 60 * 10 :
                    #voting time has ended             
                    self.log.debug("timeout for for planet %i ended" % planetuid)       
                    requestToDelete.append(planetuid)
                    attackToCancel.append(planetuid)
                    
#                    if planetuid in self.attackersAsked :
#                        self.log.debug("found some voters")
#                        for key in sorted(self.attackersAsked[planetuid].keys(), reverse=True) :
#                            if len(self.attackersAsked[planetuid][key]) > 0 :
#                                newAttacker = random.choice(self.attackersAsked[planetuid][key]) 
#                                self.log.debug("found an new attacker : %i" % newAttacker)
#                                self.attacks.resetState(planetuid)
#                                
#                                query = QSqlQuery(self.db)
#                                query.prepare("UPDATE `attacks` SET `uid_player`= ?, attack_time = NOW() WHERE `uid_planet` = ?")
#                                query.addBindValue(planetuid)
#                                query.addBindValue(newAttacker)
#                                if not query.exec_() :
#                                    self.log.debug(query.lastError())
#                                break        
#                    else :
                        
                        
                        

            sendToAll = False
            
            if len(requestToDelete) > 0 :
                sendToAll = True
                for uid in requestToDelete :
                    del self.attackOnHold[uid]
            
            for uid in attackToCancel :
                sendToAll = True
                self.attacks.cancelAttack(uid)
                              
            
            if sendToAll == True :
                self.attacks.update()
                self.sendAttackToAll()
                        

        except :
            self.log.exception("Something awful happened when checking attack wait !")        


    def cancelAttack(self, uid):
        self.log.debug("canceling attack on planet %i" % uid)
        if uid in self.defendersOnHold :
            del self.defendersOnHold[uid]        
        self.attacks.cancelAttack(uid)


    def payPlayer(self, uid, amount, add=True):
        for conn in self.recorders :
            if conn.uid == int(uid) :
                
                if add :
                    conn.addCredits(amount * (conn.rank+1))
                    self.log.debug("pay player %i %i credits" % (int(uid), amount * (conn.rank+1)))
                else :
                    conn.addCredits(amount * conn.rank)
                    self.log.debug("pay player %i %i credits" % (int(uid), amount * conn.rank))
                return
    
    def getAvatarName(self, uid):
        for conn in self.recorders :
            if conn.uid == int(uid):
                return conn.name

        # falling back
        query = QSqlQuery(self.db)
        query.prepare("SELECT name FROM avatars WHERE uid = ? and alive = 1;")
        query.addBindValue(uid)
        query.exec_()
        if query.size() > 0:
            query.first()
            return str(query.value(0))    
        
        return None


    def getAvatarRank(self, uid):
        for conn in self.recorders :
            if conn.uid == int(uid):
                return conn.rank
        
        # falling back
        query = QSqlQuery(self.db)
        query.prepare("SELECT rank FROM avatars WHERE uid = ? and alive = 1;")
        query.addBindValue(uid)
        query.exec_()
        if query.size() > 0:
            query.first()
            return int(query.value(0))    
        
        return None
        
    def getAvatarUid(self, uid):
        # replace with the correct function (mysql)
        for conn in self.recorders :
            if conn.uid == int(uid):
                return conn.avataruid
        
        # falling back
        query = QSqlQuery(self.db)
        query.prepare("SELECT id FROM avatars WHERE uid = ? and alive = 1;")
        query.addBindValue(uid)
        query.exec_()
        if query.size() > 0:
            query.first()
            return int(query.value(0))           
            
        return None
    
    def sendUpgrades(self, uid):
        for conn in self.recorders :
            if conn.uid == int(uid):
                conn.send_temporary_items()
                return 
                
    def sendToConn(self, uid, command):
        for conn in self.recorders :
            if conn.uid == int(uid):
                conn.sendJSON(command)
                self.log.debug("sending command %s to %i" % (str(command), int(uid)))
                return True
        return False

    def setConnState(self, uid, state):
        for conn in self.recorders :
            if conn.uid == int(uid) :
                conn.inBattle = state
                
    def getConnState(self, uid):
        for conn in self.recorders :
            if conn.uid == int(uid) :
                return conn.isAvailableForBattle()
            
        return False
        
    def removePlanetUpgrade(self, planetuid, faction):
        query = QSqlQuery(self.db)

        query.prepare("UPDATE planets_defense LEFT JOIN static_defenses ON static_defenses.`id` = planets_defense.itemuid SET amount=0 WHERE `planetuid`= ? AND faction = ? ")
        query.addBindValue(planetuid)
        query.addBindValue(faction)
        if not query.exec_():       
            self.log.warning(query.lastError())

        slaves = self.domination.getDominantSlaves(faction)
        for slave in slaves:
            query.prepare("UPDATE planets_defense LEFT JOIN static_defenses ON static_defenses.`id` = planets_defense.itemuid SET amount=0 WHERE `planetuid`= ? AND faction = ? ")
            query.addBindValue(planetuid)
            query.addBindValue(slave)
            if not query.exec_():       
                self.log.warning(query.lastError())        
        
        self.planetaryDefenses.update()
        self.sendPlanetDefenseUpdateToAll(planetuid) 

    def registerGameResult(self, planetuid, win = True):
        ''' apply a game result (win = attack is won) '''
        try :
            if planetuid in self.defendersOnHold :
                del self.defendersOnHold[planetuid]
            attackersuid = self.attacks.getTeamUids(planetuid, 1)
            defendersuid = self.attacks.getTeamUids(planetuid, 2)
            
            
            for uid in attackersuid :
                self.setConnState(uid, False)
            for uid in defendersuid :
                self.setConnState(uid, False)

            rankAttackers = self.attacks.getCumulatedRank(planetuid, 1)
            rankDefenders = self.attacks.getCumulatedRank(planetuid, 2)

            self.log.info("registering a attack result for planet %i" % planetuid)
            if len(attackersuid) == 0 :
                self.log.error("Attacker not found")
                return
            else:
                attackeruid = attackersuid[0]
                self.log.info("Attacker was %i" % attackeruid)
            
            attackFaction = self.attacks.getFirstFaction(planetuid)
            defenseFaction = self.attacks.getSecondFaction(planetuid)
            
            if win : 
                # paying the attackers
                for uid in attackersuid :
                    rankPlayer = self.attacks.getRank(planetuid, uid)
                    query = QSqlQuery(self.db)
                    query.prepare("UPDATE `avatars` SET `credits`= LEAST(credits+?, 1000+`rank`*1000), victories=victories+1 WHERE uid = ? AND alive = 1")
                    query.addBindValue((WIN_PAID + (WIN_PAID * rankPlayer) )+ ((WIN_PAID/2) * rankDefenders))
                    query.addBindValue(uid)
                    query.exec_()
                    self.log.debug("Paying player %i for the attack" % uid)
                    self.updatePlayer(uid)
                    
                self.changeOccupation(planetuid, attackFaction)
                self.attacks.resetState(planetuid)
                self.attacks.removeDefenders(planetuid)
                self.attacks.setUndefended(planetuid)
                self.updateAttackList()
                self.sendAttackToAll()            
            else :
                #register a successfull defense !
                self.log.debug("Planet %i defended !" % planetuid)
                
                for uid in self.attacks.getTeamUids(planetuid, 2) :
                    rankPlayer = self.attacks.getRank(planetuid, uid)
                    query = QSqlQuery(self.db)
                    query.prepare("UPDATE `avatars` SET `credits`= LEAST(credits+?, 1000+`rank`*1000), victories=victories+1 WHERE uid = ? AND alive = 1")
                    query.addBindValue(WIN_PAID + (WIN_PAID * rankPlayer) + ((WIN_PAID/2) * rankAttackers))
                    query.addBindValue(uid)
                    query.exec_()
                    self.log.debug("Paying player %i  for the defense" % uid)
                    self.updatePlayer(uid)
                    self.changeOccupation(planetuid, defenseFaction, defense=True)
                    
                self.attacks.cancelAttack(planetuid)
                self.updateAttackList()
                self.sendAttackToAll()
            

        except :
            self.log.exception("Something awful happened when registering an attack !")            



    def checkDomination(self, winner, loser):
        self.log.debug("checking domination of %i by %i" %(loser, winner))
        if self.domination.isDominated(loser) :
            self.log.debug("faction %i was already dominated by %i" %(loser, winner))
            return
        
        query = QSqlQuery(self.db)
        if loser == 0:
            query.prepare("SELECT count(id) FROM `planets` WHERE uef > ? AND visible = 1")
            self.log.debug("checking faction %i" %(loser))
            query.addBindValue(ATTACK_THRESHOLD)
        elif loser == 1:
            query.prepare("SELECT count(id) FROM `planets` WHERE aeon > ? AND visible = 1")
            self.log.debug("checking faction %i" %(loser))
            query.addBindValue(ATTACK_THRESHOLD)
        elif loser == 2:
            query.prepare("SELECT count(id) FROM `planets` WHERE cybran > ? AND visible = 1")
            self.log.debug("checking faction %i" %(loser))
            query.addBindValue(ATTACK_THRESHOLD)
        else :
            query.prepare("SELECT count(id) FROM `planets` WHERE seraphim > ? AND visible = 1")
            self.log.debug("checking faction %i" %(loser))
            query.addBindValue(ATTACK_THRESHOLD)   
            
        if query.exec_():
            if query.size() != 0:
                query.first()
                numPlanet = int(query.value(0))
                if numPlanet == 0:
                    # the losing faction is dominated !
    
                    self.log.debug("faction %i is dominated by %i" %(loser, winner))
                    self.domination.add(winner, loser)
                    self.newsFeed.domination(winner, loser)
                    
                    for conn in self.recorders :
                        if conn.faction == loser :
                            self.sendToConn(conn.uid, dict(command="dominated", master = winner))
                            self.sendToConn(conn.uid, dict(command="notice", style="info", text="Your faction is now dominated by the %s.\nFrom now, you will fight for them !" % FACTIONS[winner]))
                            conn.dominatedBy = winner
                            
                        if conn.faction == winner :    
                            self.sendToConn(conn.uid, dict(command="notice", style="info", text="Your faction is now dominating the %s.\nFrom now, they will fight for you, and you will have free access to their technology !" % FACTIONS[loser]))
                    
                    self.log.debug("All players are warn")


    def changeOccupation(self, planetuid, faction, defense=False):
        ''' change occupation on a planet'''
        
        fullSwitch = False
        if faction == None:
            self.log.warning("change occupation : No attacker found for %i" % planetuid)
            return
        
        idxControl = faction
        self.updateGalaxy()
        uef         = self.planets[planetuid]["uef"]
        aeon        = self.planets[planetuid]["aeon"]
        cybran      = self.planets[planetuid]["cybran"]
        seraphim    = self.planets[planetuid]["seraphim"]
        controls = [uef, aeon, cybran, seraphim]

        self.log.debug("Old planet occupation %f %f %f %f" % (controls[0], controls[1], controls[2], controls[3]))
        
        others = 1.0 - controls[idxControl]
        
        if defense == False and controls[idxControl] < CONTROL_THRESHOLD and (controls[idxControl] + ATTACK_WIN_RATIO) >= CONTROL_THRESHOLD :
            self.newsFeed.planetFlipped(planetuid, faction) 
        
        controls[idxControl] = controls[idxControl] + ATTACK_WIN_RATIO
        
       
        if controls[idxControl] >= 1 :
            self.log.debug("full switch")
            fullSwitch = True
            # attack may stop
            self.attacks.cancelAttack(planetuid)
            # defenses are destroyed
            
            
            for i in range(len(controls)):
                if i == idxControl:
                    controls[i] = 1
                else:        
                    controls[i] = 0
                          
        else :
            newRatioOther = others / (1.0 - controls[faction])
            for i in range(len(controls)):
                if i != idxControl:
                    controls[i] =  controls[i] / newRatioOther

        for i in range(len(controls)):
            if controls[i] < ATTACK_THRESHOLD :
                self.log.debug("removing defense for faction %i on planet %i" %(i, planetuid))
                self.removePlanetUpgrade(planetuid, i)

                  

        self.log.debug("New planet occupation %f %f %f %f" % (controls[0], controls[1], controls[2], controls[3]))   
        query = QSqlQuery(self.db)
        query.prepare("UPDATE `planets` SET `uef`=?,`aeon`=?,`cybran`=?,`seraphim`=? WHERE id = ?")
        query.addBindValue(controls[0])
        query.addBindValue(controls[1])
        query.addBindValue(controls[2])
        query.addBindValue(controls[3])
        query.addBindValue(planetuid)
        query.exec_()
        
        if not defense:
            self.log.debug("checking domination")
            for i in range(len(controls)):
                if i != idxControl:
                    self.checkDomination(faction, i)

        self.updateGalaxy() 
        self.sendPlanetUpdateToAll(planetuid)  
        return fullSwitch

    def attacksCheck(self):
        ''' checking the attacks charges '''
        try :
            toCheck = {}
            self.updateAttackList()
            didSomething= False
            for uid in self.attacks.attacks :

                planetuid = self.attacks.attacks[uid].getPlanet()
                timeAttack = self.attacks.getTimeAttack(planetuid)

                if timeAttack != None and self.attacks.isDefended(planetuid) == False and self.attacks.isOnHold(planetuid) == False:
                    
                    factionAttacker = self.attacks.getFirstFaction(planetuid)
                    if timeAttack > (60*10):
                        #we are reaching a step in the attack
                        query = QSqlQuery(self.db)
                        query.prepare("UPDATE `attacks` SET `attack_time`= NOW() WHERE id = ?")
                        query.addBindValue(uid)
                        if query.exec_():  
                            toCheck[planetuid] = factionAttacker
            
            for planetuid in toCheck:
                didSomething= True
                factionAttacker = toCheck[planetuid]
                self.changeOccupation(planetuid, factionAttacker)
            
            if didSomething:
                self.updateAttackList()
                self.sendAttackToAll()

        except :
            self.log.exception("Something awful happened when checking attack !")

    
    def influenceCheck(self):
        '''checking influence of planet'''
        try :
            
            self.updateGalaxy()
            changed = []
            for planetuid in self.planets:
                if self.planets[planetuid]["visible"] == False:
                    continue
                self.log.debug("Checking influence for %i" % planetuid)
                
                if self.attacks.isDefended(planetuid) == True:
                    continue
                if self.attacks.isUnderAttack(planetuid) == True:  
                    continue
                
                multiplier = self.computeInfluence(planetuid)
                
                uef         = self.planets[planetuid]["uef"]
                aeon        = self.planets[planetuid]["aeon"]
                cybran      = self.planets[planetuid]["cybran"]
                seraphim    = self.planets[planetuid]["seraphim"]
                orig_controls = [uef, aeon, cybran, seraphim]                      
                
                controls = [max(0,x - (0.005*(1.0-y))) for x, y in zip(orig_controls, multiplier)]
                
                if orig_controls[0] != controls[0] or orig_controls[1] != controls[1] or orig_controls[2] != controls[2] or orig_controls[3] != controls[3]:
                
                    self.log.debug("Old influence : %f %f %f %f" % (orig_controls[0], orig_controls[1], orig_controls[2], orig_controls[3]))
                    self.log.debug("Multipliers : %f %f %f %f" % (multiplier[0], multiplier[1], multiplier[2], multiplier[3]))
                    self.log.debug("New Influence : %f %f %f %f" % (controls[0], controls[1], controls[2], controls[3]))
                    
                    query = QSqlQuery(self.db)
                    query.prepare("UPDATE `planets` SET `uef`=?,`aeon`=?,`cybran`=?,`seraphim`=? WHERE id = ?")
                    query.addBindValue(controls[0])
                    query.addBindValue(controls[1])
                    query.addBindValue(controls[2])
                    query.addBindValue(controls[3])
                    query.addBindValue(planetuid)
                    query.exec_()
                    
                    bestInfluence = multiplier.index(max(multiplier))
                    for i in range(len(controls)):
                        if orig_controls[i] > ATTACK_THRESHOLD and controls[i] < ATTACK_THRESHOLD:
                            self.checkDomination(bestInfluence, i)
            
                    changed.append(planetuid)

                
                        
            if len(changed) > 0:
                self.updateGalaxy() 
                for planetuid in changed:
                    self.sendPlanetUpdateToAll(planetuid)    
                                
                    

        except :
            self.log.exception("Something awful happened when checking influences !")        
    

    def sendPlanetDefenseUpdateToAll(self, planetuid):
        for conn in self.recorders :
            conn.sendDefense(planetuid, False)    
            
    def sendPlanetUpdateToAll(self, planetuid):
        for conn in self.recorders :
            conn.sendPlanet(planetuid)    

    def sendNews(self):
        for conn in self.recorders :
            conn.sendNews()

    def updateAttackList(self):
        self.attacks.update()                  
                
                
                
    def getConnected(self, siteIdx):
        ''' This return all the sites that are linked to the one provided'''
        connections = []
        if siteIdx in self.links :
            for idx in self.links[siteIdx] :
                if idx != siteIdx :
                    connections.append(idx)            
        
        for otherSite in self.links :
            if siteIdx in self.links[otherSite] and siteIdx != otherSite :
                    connections.append(otherSite)
        return connections                

    def computeInfluence(self, siteIdx):
        '''compute the number of links between two planets'''
        #return [0,0,0,0]
        neighbors = self.getConnected(siteIdx)

        controlsPercent = [0,0,0,0]
        if neighbors == 0:
            return controlsPercent
        for idx in neighbors:
            uef         = self.planets[idx]["uef"]
            aeon        = self.planets[idx]["aeon"]
            cybran      = self.planets[idx]["cybran"]
            seraphim    = self.planets[idx]["seraphim"]
            controls = [uef, aeon, cybran, seraphim]            
            
            controlsPercent = [x + y for x, y in zip(controlsPercent, controls)]

        vals = [float(x) / float(len(neighbors)) for x in controlsPercent]
        
        return [ 1.0 if x >= 0.5 else x for x in vals]

    def getPlanetsLinked(self, siteIdx, distance=3, numConn = 0, previous=[]):
        if numConn == 0:
            previous = []
        else:
            if not siteIdx in previous:
                previous.append(siteIdx)

        numConn = numConn+1 
        if numConn == distance:
            return previous
        
        for idx in self.getConnected(siteIdx) :
            if not idx in previous:
                self.getPlanetsLinked(idx, distance, numConn, previous) 
        
        return previous        

    def computeDistance(self, siteIdx, otherSiteIdx, maxConn = 5, numConn = 0, previous=[]):
        '''compute the number of links between two planets'''
        if numConn == 0:
            previous = []
        numConn = numConn+1 
        if numConn == maxConn:
            return -1
        previous.append(siteIdx)
        

        for idx in self.getConnected(siteIdx) :
            if otherSiteIdx == idx:
                return numConn
            else:
                if not idx in previous:
                    result = self.computeDistance(idx, otherSiteIdx, maxConn, numConn, previous) 
                    if result != -1:
                        return result
        return -1

                
    def updateGalaxy(self):
        try :
            query = QSqlQuery(self.db)
            query.prepare("SELECT planets.id, X(position), Y(position), size, planets.name, planets.description, uef, cybran, aeon, seraphim, links, texture, planet_maps.mapuid, faf_lobby.table_map.filename, visible, sector, FLOOR(max_players/2) FROM `planets` LEFT JOIN planet_maps ON planet_maps.planetuid = planets.id LEFT JOIN faf_lobby.table_map ON planet_maps.`mapuid` = faf_lobby.table_map.id WHERE 1")
            query.exec_()
            
            if query.size() > 0 :
                self.planets = {}
                self.links = {}
                #query.first()
                while next(query) :
                    uid = int(query.value(0))
                    posx = round(query.value(1))
                    posy = round(query.value(2))
                    size = float(query.value(3)) 
                    
                    name = str(query.value(4))
                    desc = str(query.value(5))
                    
                    uef = float(query.value(6))
                    cybran = float(query.value(7))
                    aeon = float(query.value(8))
                    sera = float(query.value(9))
                                   
                    links = json.loads(str(query.value(10)))
                    
                    texture = str(query.value(11))
                    md5tex = self.getMd5(os.path.join(TEXPATH, texture + ".png"))

                    visible = bool(query.value(14))
                    sector = int(query.value(15))

                    
                    if visible:
                        mapuid = int(query.value(12))
                        mapname = str(query.value(13))
                        maxplayer = int(query.value(16))
                    else:
                        mapuid = -1
                        mapname = ""
                        maxplayer = 0
                    
                    self.planets[uid] = (dict(uid = uid, posx = posx, posy = posy, size = size, name = name, desc = desc, uef = uef, cybran = cybran, aeon = aeon, seraphim = sera, links = links, texture = texture, md5tex = md5tex, mapuid=mapuid, mapname=mapname, visible=visible, sector=sector, maxplayer=maxplayer))
                    self.links[uid] = links
            
            #updating planetary defenses
            self.planetaryDefenses.update()
            
        except :
            self.log.exception("Something awful happened when updating galaxy !")
            
    def updatePlayer(self, uid):
        self.log.debug("sending player update to a player")
        for conn in self.recorders :
            if conn.uid == uid :
                conn.updatePlayerStats()

        
    def updateAllPlayers(self):
        self.log.debug("sending player update to all players")
        for conn in self.recorders :
            conn.updatePlayerStats()
             
        

    def incomingConnection(self, socketId):
        self.log.debug("Incoming client Connection")
        reload(lobby) 
        self.recorders.append(lobby.ClientModule(socketId, self))           

    def removeRecorder(self, recorder):
        if recorder in self.recorders:
            self.recorders.remove(recorder)
            recorder.deleteLater()



