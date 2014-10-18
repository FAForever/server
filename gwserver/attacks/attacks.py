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

from PySide.QtSql import QSqlQuery
import time

#ATTACK_PERDIOD = 1 * 60 * 60 # 1 hour
ATTACK_WIN_RATIO = 0.1
WIN_PAID = 100

class AttackState:
    '''
    Various states the game can be in.
    '''
    WAIT                = 0
    SECOND_IN_COMMAND   = 1
    HOSTED              = 2
    LAUNCHED            = 3
    LAUNCHING           = 4


class Player(object) :
    def __init__(self, uid, faction, rank, name):
        self.uid = uid
        self.faction = faction
        self.inGame = False
        self.rank = rank
        self.name = name
        

class attack(object):
    def __init__(self, planet, timeAttack, parent=None):
        self.parent = parent
        
        self.planet = planet
        
        self.team1 = {}
        self.team2 = {}
        
        self.timeAttack = timeAttack
        
        self.reinforcements = None
        
        self.maxPlayers = 1
        
        self.state = AttackState.WAIT
        self.defended = False
        
        self.team1faction = None
        self.team2faction = None
        
        self.mutualAttack = False
        
        self.cancel = 0
        self.uuid = 0
    
        self.joined = []
    
    def registerJoin(self, playeruid):
        if not playeruid in self.joined:
            self.joined.append(playeruid)
        
    def cleanJoin(self):
        self.joined = []
        
    def hasJoined(self, playeruid):
        if playeruid in self.joined:
            return True
        return False
    
    def setReinforcements(self, reinforcements):
        self.reinforcements = reinforcements
        
    def getReinforcements(self):
        return self.reinforcements  
    
    def getCancel(self):
        return self.cancel
    
    def getMaxPlayers(self):
        return self.maxPlayers
    
    def getNumPlayers(self, team):
        if team == 1 :
            return len(self.team1)
        else :
            return len(self.team2)
    
    def teamIsFull(self, team):
        if self.getNumPlayers(team) >= self.getMaxPlayers() :
            return True
        else :
            return False
        
    def registerCancel(self):
        self.cancel = self.cancel + 1
    
    def emptyTeam(self, team):
        if team == 1:
            self.team1 = {}
        else:
            self.team2 = {}
    
    def getTeam(self, team):
        if team == 1 :
            return self.team1
        else :
            return self.team2
    
    def setMutualAttack(self):
        self.mutualAttack = True
        
    def isMutualAttack(self):
        return self.mutualAttack
    
    def getState(self):
        return self.state
    
    def setState(self, state):
        self.state = state
    
    def isDefended(self):
        return self.defended
        
    
    def getTimeAttack(self):
        return self.timeAttack
    
    def getRank(self, uid):
        if uid in self.team1:
            return self.team1[uid].rank
        elif uid in self.team2:
            return self.team2[uid].rank
        return 0
    
    def getCumulatedRank(self, team):
        count = 0
        if team == 1 :
            for uid in self.team1 :
                count = count + self.team1[uid].rank
        else :
            for uid in self.team2 :
                count = count + self.team2[uid].rank
             
        return count

    
    def addTeam1(self, uid, faction):  
        rank, name = self.parent.findPlayerInfos(uid)
        if name == None or rank == None:
            return
        if not uid in self.team1:
            self.team1[uid] = Player(uid, faction, rank, name)
            self.team1faction = faction

    def addTeam2(self, uid, faction):
        rank, name = self.parent.findPlayerInfos(uid)
        if name == None or rank == None:
            return
        if not uid in self.team2:
            self.team2[uid] = Player(uid, faction, rank, name)
            self.team2faction = faction
    
    def removePlayer(self, uid):
        if uid in self.team1:
            del self.team1[uid]
        if uid in self.team2:
            del self.team2[uid]
        
                
    def getPlanet(self):
        return self.planet
    
    def getPlayerRank(self, uid):
        if uid in self.team1 :
            return self.team1[uid].rank
        elif uid in self.team2 :
            return self.team2[uid].rank
        else:
            return 0
            
    
    def isTimeout(self):
        if self.defended == True and self.state == AttackState.WAIT:
            return False
        
        if self.timeAttack <= 0 :
            return True
   
    def setDefended(self):
        self.defended = True

    def getFaction(self, team):
        if team == 1 :
            return self.team1faction
        else :
            return self.team2faction

    def getTeamUids(self, team):
        if team == 1 :
            return self.team1.keys() 
        else :
            return self.team2.keys()        
        return None
    
    def isPlayerIn(self, uid):
        if uid in self.team1 or uid in self.team2 :
            return True
        return False
    
    def update(self, playeruid, timeAttack, defended):
        self.timeAttack = timeAttack
        self.defended = defended
        #self.team1 = {}
        self.addTeam1(playeruid, self.team1faction)
        
    def setUuid(self, uuid):
        self.uuid = uuid

    def getUuid(self):
        return self.uuid
    
class Attacks(object):
    def __init__(self, parent = None):
        self.parent = parent
        self.attacks = {}
        
    def clear(self) :
        self.attacks = {}
        

    def update(self):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT id, uid_player, uid_planet, attack_time, faction, defended, IFNULL(dominant,-1) FROM `attacks` LEFT JOIN accounts ON accounts.uid = uid_player LEFT JOIN domination on faction = domination.slave WHERE 1")
        query.exec_()
        if query.size() > 0 :
            allUids = []
            
            while query.next() :
                uid       = int(query.value(0))
                playeruid = int(query.value(1))
                planetuid = int(query.value(2))
                attack    = (time.time() - query.value(3).toTime_t())
                faction   = int(query.value(4)) 

                if int(query.value(6)) != -1:
                    faction = int(query.value(6))
                
                defended  = bool(query.value(5))
                allUids.append(uid)
                
                if not uid in self.attacks :
                    self.addAttack(uid, playeruid, faction, planetuid, attack, defended)
                else :
                    self.updateAttack(uid, playeruid, attack, defended)

            toDelete = []
            for uid in self.attacks :
                if not uid in allUids :
                    toDelete.append(uid)
            for uid in toDelete :
                del self.attacks[uid]
                
        else :
            self.attacks = {}

    def updateAttack(self, uid, playeuid, timeAttack, defended):
        self.attacks[uid].update(playeuid, timeAttack, defended)

    def addAttack(self, uid, playeruid, faction, planetuid, timeAttack, defended) :
        newAttack = attack(planetuid, timeAttack, self.parent)
        newAttack.addTeam1(playeruid, faction)
        
        if defended :
            newAttack.setDefended()

        self.attacks[uid] = newAttack 

    def addAttacker(self, planetuid, playeruid, faction):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].addTeam1(playeruid, faction)
                return        
        
    def addDefenser(self, planetuid, playeruid, faction):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].addTeam2(playeruid, faction)
                return
    
    def removePlayer(self, planetuid, playeruid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].removePlayer(playeruid)
                return

    
    def getPlayerRank(self, planetuid, playeruid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getPlayerRank(playeruid)
        return 0

    def getRank(self, planetuid, uid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getRank(uid)
        return 0 
        
    def getCumulatedRank(self, planetuid, team):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getCumulatedRank(team)
        return 0        
    
    def getTimeAttack(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getTimeAttack()
        return None
    # def getTimeoutAttacks(self):
    #     uids = []
    #     for uid in self.attacks :
    #         if self.attacks[uid].isTimeout() :
    #             uids.append(self.attacks[uid].getPlanet())
    #     return uids
        
    def getFirstFaction(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getFaction(1)
        return None

    def getSecondFaction(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getFaction(2)
        return None
    
    def getTeamUids(self, planetuid, team):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getTeamUids(team)
        return []        
    
    def getCancel(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getCancel()
        return 0

    def registerCancel(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].registerCancel()
            
    def getAttackFrom(self, playeruid, planetuid = None):
        uids = []
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() != planetuid :
                if self.attacks[uid].isPlayerIn(playeruid) :
                    uids.append(self.attacks[uid].getPlanet())
        return uids


   
    def checkAttackNumber(self, useruid, offset=0):
        number = offset
        for uid in self.attacks :
            if self.attacks[uid].isPlayerIn(useruid) :
                number = number + 1 
        if number > 0 :
            return True
        else :
            return False
    
    def removeAllJoin(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].cleanJoin()
    
    def registerJoin(self, planetuid, playeruid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].registerJoin(playeruid)
                
    
    def hasJoined(self, planetuid, playeruid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].hasJoined(playeruid)
        return False
    
    def cancelAttack(self, planetuid):
        query = QSqlQuery(self.parent.db)
        query.prepare("DELETE FROM `attacks` WHERE `uid_planet` = ?")
        query.addBindValue(planetuid)
        query.exec_()        
        self.update()
    
    def isDefended(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].isDefended()
        return False        
    
    def isUnderAttack(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return True
        return False
    
    def isMutualAttack(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].isMutualAttack()
        return False    


    def setMutualAttack(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].setMutualAttack()
        return False   
    
    def resetState(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].setState(AttackState.WAIT)
                return    
    
    def setUndefended(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].defended = False
                query = QSqlQuery(self.parent.db)
                query.prepare("UPDATE `attacks` SET `defended` = 0 WHERE id  = ?")
                query.addBindValue(uid)
                query.exec_()
                return
    
    def exists(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return True
        return False
    
    def isWaiting(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                if self.attacks[uid].getState() == AttackState.WAIT :
                    return True
                else :
                    return False
        return False          
    
    def isHosted(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                if self.attacks[uid].getState() == AttackState.HOSTED :
                    return True
                else :
                    return False
        return False        
    
    def isOnHold(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                if self.attacks[uid].getState() == AttackState.SECOND_IN_COMMAND :
                    return True
                else :
                    return False
        return False 
    
    def setHosted(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].setState(AttackState.HOSTED)
                return     

    def setLaunching(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].setState(AttackState.LAUNCHING)
                return   
            
    def setLaunched(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].setState(AttackState.LAUNCHED)
                return   

               
    def setOnHold(self, planetuid) :
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].setState(AttackState.SECOND_IN_COMMAND)
                return        


    def removeAttackers(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].emptyTeam(1)
                return True
        return False
    
    def removeDefenders(self, planetuid):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].emptyTeam(2)
                return True
        return False
            
    def isTeamFull(self, planetuid, team):
        for uid in self.attacks :
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].teamIsFull(team)
        return None        
        
    def cleanGames(self, playeruid):
        uids = []
        for uid in self.attacks :
            if self.attacks[uid].getState() != AttackState.LAUNCHED:
                if self.attacks[uid].isPlayerIn(playeruid) :
                    uids.append(self.attacks[uid].getPlanet())
        return uids
    

    def setGameUid(self, planetuid, uuid):
        ''' add the game uuid'''
        for uid in self.attacks:
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].setUuid(uuid)
                return        

    def getGameUid(self, planetuid):
        ''' add the game uuid'''
        for uid in self.attacks:
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getUuid()
        return None
                

    def setReinforcements(self, planetuid, reinforcements):
        for uid in self.attacks:
            if self.attacks[uid].getPlanet() == planetuid :
                self.attacks[uid].setReinforcements(reinforcements)      

    def getReinforcements(self, planetuid):
        for uid in self.attacks:
            if self.attacks[uid].getPlanet() == planetuid :
                return self.attacks[uid].getReinforcements()      
        return None
    
    def getList(self, rank):
        attacks = {}
      

        for uid in self.attacks :
            playeruids = self.attacks[uid].getTeamUids(1)
            if playeruids :
                playeruid = playeruids[0]
            
                if not playeruid in attacks : 
                    attacks[playeruid] = {}

                attackers = []
                if rank != 0 :
                    attackersList = self.attacks[uid].getTeam(1)
                    for puid in attackersList :
                        if rank == 1 :
                            attackers.append((attackersList[puid].rank, "Unknown"))
                        else :
                            attackers.append((attackersList[puid].rank, attackersList[puid].name))
                if self.attacks[uid].getFaction(1) == None:
                    continue
                
                if self.attacks[uid].getState() == AttackState.SECOND_IN_COMMAND :
                    attacks[playeruid][self.attacks[uid].getPlanet()] = dict(onHold = True, faction = self.attacks[uid].getFaction(1), timeAttack = self.attacks[uid].getTimeAttack(), defended = self.attacks[uid].isDefended(), attackers = attackers)
                else :
                    attacks[playeruid][self.attacks[uid].getPlanet()] = dict(onHold = False, faction = self.attacks[uid].getFaction(1), timeAttack = self.attacks[uid].getTimeAttack(), defended = self.attacks[uid].isDefended(), attackers = attackers)
    

        
        return attacks