from functools import reduce

from PySide.QtCore import QObject
from PySide.QtCore import QByteArray, QDataStream, QIODevice, QFile, QCoreApplication
from PySide import QtNetwork
from PySide.QtSql import *
import config
from config import Config
import server.db as db

import asyncio
import os
import logging
import json
import urllib.request, urllib.error, urllib.parse
import datetime

class replayServerThread(QObject):  # pragma: no cover
    """
    FA server thread spawned upon every incoming connection to
    prevent collisions.
    """
    
    
    def __init__(self, socketId, parent=None):
        super(replayServerThread, self).__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.socket = QtNetwork.QTcpSocket(self)
        self.socket.setSocketDescriptor(socketId)
        self.parent = parent
        
        if self.socket.state() == 3 and self.socket.isValid():
            
            self.nextBlockSize = 0
    
            self.blockSize = 0   

            self.socket.readyRead.connect(self.readDatas)
            self.socket.disconnected.connect(self.disconnection)
            self.socket.error.connect(self.displayError)
            self.parent.db.open()   

    def lock(self):
        pass
#        query = QSqlQuery(self.parent.db)
#        query.prepare("SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED ;")
#        query.exec_()
        
    def unlock(self):
        pass
#        query = QSqlQuery(self.parent.db)
#        query.prepare("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ ;")
#        query.exec_()        

    @asyncio.coroutine
    def command_modvault_search(self, message):
        """that function is used by the mod vault to search for mods!"""

        typemod = message["typemod"]
        search = message["search"]
        
        descriptionField =  ".*[[:space:]]"+search+"[[:space:]].*"
        nameField = "%" + search + "%"

        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()
            queryStr = "SELECT `uid`, `t`.`name`,`version`,`author`,`ui`,`date`,`downloads`,`likes`,`played`,`description`,`filename`,`icon` \
                        FROM     (     SELECT `name`, MAX(`version`) AS max_version \
                                        FROM `table_mod`   \
                                        WHERE (`name` LIKE %s OR `description` REGEXP %s OR `author` LIKE %s)"

            if typemod != 2:
                queryStr += "AND `ui` = " + typemod

            queryStr += "GROUP BY `name` \
                         ORDER BY `id` DESC   \
                         LIMIT 0,100 \
                            ) AS m \
                    INNER JOIN `table_mod` AS t \
                        ON t.`name`= m.`name` \
                        AND t.`version`= m.max_version;"

            modList = []
            yield from cursor.execute(queryStr, nameField, descriptionField, nameField)
            for i in range(0, cursor.rowcount):
                uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon = yield from cursor.fetchone()
                date = date.toTime_t()
                link = Config['content_url'] + "vault/" + filename

                thumbstr = ""
                if icon != "":
                    thumbstr = Config['content_url'] + "vault/mods_thumbs/" + urllib.parse.quote(icon)
                
                modList.append(dict(thumbnail=thumbstr,link=link,bugreports=[],comments=[],description=description,played=played,likes=likes,downloads=downloads,date=date, uid=uid, name=name, version=version, author=author,ui=ui))

        out = dict(command="modvault_list_info", modList = modList)
        self.sendJSON(out)

    def command_coop_stats(self, message):
        missionuid = message["mission"]
        table = message["type"]

        query = QSqlQuery(self.parent.db)
        if table == 0:
            query.prepare("SELECT login, gameuid, leader.time, leader.secondary FROM\
                              (\
                            SELECT time, gameuid, secondary\
                            FROM `coop_leaderboard`\
                            WHERE mission =?\
                            ORDER BY time\
                            LIMIT 0,50\
                            ) leader\
                            INNER JOIN game_player_stats ON game_player_stats.gameid = leader.gameuid\
                            INNER JOIN login ON game_player_stats.playerid = login.id")
            query.addBindValue(missionuid)
        else:
            query.prepare("SELECT login, gameuid, leader.time, leader.secondary FROM\
                          (\
                        SELECT time, gameuid, secondary\
                        FROM `coop_leaderboard`\
                        WHERE mission =?\
                        AND\
                        (\
                        SELECT count(*) FROM game_player_stats\
                        WHERE\
                        gameid = gameuid\
                        ) = ?\
                        ORDER BY time\
                        LIMIT 0,50\
                        ) leader\
                        INNER JOIN game_player_stats ON game_player_stats.gameid = leader.gameuid\
                        INNER JOIN login ON game_player_stats.playerid = login.id")
            query.addBindValue(missionuid)
            query.addBindValue(table)
        
 
        if not query.exec_():
            self.logger.debug(query.lastQuery())
            self.logger.debug(query.lastError())
        
        missions = {}
        if query.size() > 0:
            rank = 0
            while query.next():
                uid = query.value(2)
                if not uid in missions:
                    missions[uid] = {}
                    missions[uid]= dict(rank = rank, players=[], time= query.value(2).toString("HH:mm:ss"), gameuid = query.value(1), secondary = query.value(3))
                    rank += 1
                
                players = missions[uid]["players"]
                players.append(str(query.value(0)))
                
        missionsToSend = list(range(len(missions)))
        for uid in missions:
            
            missionsToSend[missions[uid]["rank"]] = missions[uid] 

        self.sendJSON(dict(command = "coop_leaderboard", table = table, mission = missionuid, leaderboard=missionsToSend))

    def command_stats(self, message):

        typeState = message['type']
        
        if typeState == "divisions":
            league = message['league']
            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT name FROM ladder_division WHERE `league` = ?")
            query.addBindValue(league)
            query.exec_()
            
            if query.size() > 0:
                num = 0
                finalresult = []
                while query.next():
                    finalresult.append((dict(number=num, division = str(query.value(0)), league = league)))
                    num += 1
                self.sendJSON(dict(command = "stats", type = "divisions", league=league, values = finalresult))

        elif typeState == "division_table":
            league = message['league']
            division = message['division']
            query = QSqlQuery(self.parent.db)
            limit = 0
            query.prepare("SELECT `limit` FROM ladder_division WHERE id = ?")
            
            query.addBindValue((5*(league-1)) +(division+1))
            query.exec_()
            if query.size() > 0:
                query.first()
                limit = int(query.value(0))
            
            range = 0
            if league == 1:
                range = 10
            elif league == 2:
                range = 15
            elif league == 3:
                range = 20
            elif league == 4:
                range = 25
            elif league == 5:
                range = 50 
            
            limitBasse = limit - range
            
            query.prepare("SELECT login, score FROM %s JOIN login ON %s.idUser=login.id WHERE league = ? AND score <= ? AND score >= ? ORDER BY score DESC" % (config.LADDER_SEASON, config.LADDER_SEASON))
            query.addBindValue(league)
            query.addBindValue(limit)
            query.addBindValue(limitBasse)
            query.exec_()
            finalresult = []
            if query.size() > 0:
                rank = 1
                while query.next():
                    score = float(query.value(1))
                    if score !=0:
                        finalresult.append((dict(rank=rank, name = str(query.value(0)), score = score)))
                        rank += 1
                
            self.sendJSON(dict(command = "stats", type = "division_table", division=message['division'], league=message['league'], values = finalresult))


        elif typeState == "league_table":
            league = message['league']
            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT login, score FROM %s JOIN login ON %s.idUser=login.id  WHERE league = ? ORDER BY score DESC" % (config.LADDER_SEASON, config.LADDER_SEASON))
            query.addBindValue(league)
            query.exec_()

            if query.size() > 0:
                finalresult = []
                rank = 1
                while query.next():
                    score = float(query.value(1))
                    if score != 0:
                        finalresult.append((dict(rank=rank, name = str(query.value(0)), score = score)))
                        rank += 1
  
                self.sendJSON(dict(command = "stats", type = "league_table", league=league, values = finalresult))
            else:
                self.sendJSON(dict(command = "stats", type = "league_table", league=league, values = []))


        elif typeState == "global_90_days":
            name = message['player']
            query = QSqlQuery(self.parent.db)
                
            query.prepare("SELECT startTime, mean, deviation FROM `game_player_stats` LEFT JOIN game_stats ON `gameId` = game_stats.id WHERE `playerId` = (SELECT id FROM login WHERE login.login = ?) AND gameType = '0' AND `scoreTime` IS NOT NULL AND startTime > (select date_sub(now(),interval 90 day)) ORDER BY startTime DESC")
            query.addBindValue(name)
            query.exec_()

            if query.size() > 0:
                finalresult = []
                while query.next():
                    if query.value(1) != 0 and query.value(2) != 0: 
                        date = query.value(0).toString("dd.MM.yyyy")
                        time = query.value(0).toString("hh:mm")
                        if date == "" or time == "": 
                            continue                        
                        finalresult.append((dict(date=date, time = time, mean=query.value(1), dev=query.value(2))))
                   
                if len(finalresult) > 0:
                    self.sendJSON(dict(command = "stats", type = "global_90_days", player=name, values = finalresult))
                    
        elif typeState == "global_forever":
            name = message['player']
            query = QSqlQuery(self.parent.db)
                
            query.prepare("SELECT startTime, mean, deviation FROM `game_player_stats` LEFT JOIN game_stats ON `gameId` = game_stats.id WHERE `playerId` = (SELECT id FROM login WHERE login.login = ?) AND gameType = '0' AND `scoreTime` IS NOT NULL AND startTime > (select date_sub(now(),interval 365 day)) ORDER BY startTime DESC")
            query.addBindValue(name)
            query.exec_()

            if query.size() > 0:
                finalresult = []
                while query.next():
                    if query.value(1) != 0 and query.value(2) != 0:
                        date = query.value(0).toString("dd.MM.yyyy")
                        time = query.value(0).toString("hh:mm")
                        if date == "" or time == "": 
                            continue
                        finalresult.append((dict(date=date, time = time, mean=query.value(1), dev=query.value(2))))
                   
                if len(finalresult) > 0:
                    self.sendJSON(dict(command = "stats", type = "global_forever", player=name, values = finalresult))
              
        elif typeState == "ladder_maps":
            query = QSqlQuery(self.parent.db)
                
            query.prepare("SELECT `idmap` , table_map.name, filename FROM `ladder_map` LEFT JOIN table_map ON `idmap` = table_map.id")
            query.exec_()
            finalresult = []
            if query.size() > 0:
                
                while query.next():
                    finalresult.append(dict(idmap = int(query.value(0)), mapname = query.value(1), maprealname = query.value(2)))
                
                
            
            
            lastSeason = self.getLastSeason()
            
                
            query.prepare("SELECT COUNT(*) FROM  game_stats WHERE `EndTime` > ? AND `gameMod` = 6")
            query.addBindValue(str(lastSeason))
            query.exec_()
            
            if query.size() > 0:
                query.first()
                self.sendJSON(dict(command = "stats", type = "ladder_maps", values = finalresult, gamesplayed = int(query.value(0))))
            
        elif typeState == "ladder_map_stat":
            idmap = message["mapid"]

            # get correct time : last season !
            lastSeason = self.getLastSeason()
            
            stats = {}
            stats["uef_total"] = 0
            stats["cybran_total"] = 0
            stats["aeon_total"] = 0
            stats["sera_total"] = 0

            stats["uef_win"] = 0
            stats["cybran_win"] = 0
            stats["aeon_win"] = 0
            stats["sera_win"] = 0

            stats["cybran_ignore"] = 0
            stats["sera_ignore"] = 0
            stats["uef_ignore"] = 0
            stats["aeon_ignore"] = 0
            
            stats["draws"] = 0

            query = QSqlQuery(self.parent.db)
            
            games = {}
            
            query.prepare("SELECT MAX(TIME_TO_SEC(TIMEDIFF(EndTime,startTime))), AVG(TIME_TO_SEC(TIMEDIFF(EndTime,startTime))) FROM `game_player_stats` JOIN game_stats ON `gameId` = game_stats.id WHERE `EndTime` > ? AND `gameMod` = 6 AND game_stats.mapId = ? AND EndTime IS NOT NULL AND TIME_TO_SEC(TIMEDIFF(EndTime,startTime)) > 120 AND TIME_TO_SEC(TIMEDIFF(EndTime,startTime)) < 10800")
            query.addBindValue(str(lastSeason))
            query.addBindValue(idmap)
            query.exec_()
            #self.logger.debug("map " + str(idmap))
            if query.size() > 0:
                query.first()
                stats["duration_max"] = int(query.value(0))
                stats["duration_avg"] = int(query.value(1))

            query.prepare("SELECT COUNT(*) FROM `game_player_stats` JOIN game_stats ON `gameId` = game_stats.id WHERE `EndTime` > ? AND `gameMod` = 6 AND game_stats.mapId = ? AND EndTime IS NOT NULL")
            query.addBindValue(str(lastSeason))
            query.addBindValue(idmap)
            
            query.exec_()
            if query.size() > 0:
                query.first()
                stats["game_played"] = int(query.value(0))
                
            query.prepare("SELECT gameId, faction, score FROM `game_player_stats` JOIN game_stats ON `gameId` = game_stats.id WHERE `EndTime` > ? AND `gameMod` = 6 AND game_stats.mapId = ? AND EndTime IS NOT NULL")
            
            query.addBindValue(str(lastSeason))
            query.addBindValue(idmap)
            query.exec_()
            if query.size() > 0:
                
                while query.next():

                    gameId = int(query.value(0))
                    faction = int(query.value(1))
                    if faction == 1:
                        stats["uef_total"] += 1
                    elif faction == 3:
                        stats["cybran_total"] += 1
                    elif faction == 2:
                        stats["aeon_total"] += 1
                    elif faction == 4:
                        stats["sera_total"] += 1
                            
                    score = int(query.value(2))

                    player = "player2"
                    if not gameId in games:
                        games[gameId] = {}
                        player = "player1"
#                        
                    games[gameId][player] = {}
                    games[gameId][player]["faction"] = faction
                    games[gameId][player]["score"] = score

            for game in games:
                if "player2" in  games[game]:
                    if games[game]["player1"]["score"] == games[game]["player2"]["score"]:
                        stats["draws"] += 1
                    else:
                        faction = 0
                        otherfaction = 0
                        if games[game]["player1"]["score"] >  games[game]["player2"]["score"]:
                            faction = games[game]["player1"]["faction"]
                            otherfaction = games[game]["player2"]["faction"]
                        else:
                            faction = games[game]["player2"]["faction"]
                            otherfaction = games[game]["player1"]["faction"]

                        
                           
                        if faction == 1:
                            if otherfaction == faction:
                                stats["uef_ignore"] += 1
                            else:
                                stats["uef_win"] += 1
                        elif faction == 3:
                            if otherfaction == faction:
                                stats["cybran_ignore"] += 1
                            else:
                                stats["cybran_win"] += 1
                        elif faction == 2:
                            if otherfaction == faction:
                                stats["aeon_ignore"] += 1
                            else:
                                stats["aeon_win"] += 1
                        elif faction == 4:
                            if otherfaction == faction:
                                stats["sera_ignore"] += 1
                            else:
                                stats["sera_win"] += 1
                       

            self.sendJSON(dict(command = "stats", type = "ladder_map_stat", idmap = idmap, values = stats))


    def getLastSeason(self):
        now = datetime.date.today()

        if (now.month == 3 and now.day < 21) or now.month < 3:
            previous = datetime.datetime(now.year-1, 12, 21)
            
        elif (now.month == 6 and now.day < 21) or now.month < 6:
    
            previous = datetime.datetime(now.year, 0o3, 21)
            
        elif (now.month == 9 and now.day < 21) or now.month < 9:
         
            previous = datetime.datetime(now.year, 0o6, 21)
            
        else:
          
            previous = datetime.datetime(now.year, 9, 21)
        
        return previous

    def command_list(self, message):
        query = QSqlQuery(self.parent.db)
        query.setForwardOnly(True)
        query.prepare("SELECT game_stats.id, gameName AS title, map.filename AS map, startTime, EndTime , game_featuredMods.gamemod  \
                       FROM game_stats \
                       LEFT JOIN table_map AS map ON game_stats.mapId=map.id \
                       LEFT JOIN game_featuredMods ON game_stats.gameMod = game_featuredMods.id \
                       LEFT JOIN game_replays ON game_stats.id = game_replays.UID \
                       WHERE (startTime IS NOT NULL) AND (EndTime IS NOT NULL) AND (EndTime - startTime >= 4*60) \
                       AND game_replays.UID IS NOT NULL \
                       ORDER BY game_stats.id DESC \
                       LIMIT 0, 300")
       
        query.exec_()
        if  query.size() > 0:
            replays = []
            while query.next():
                replay = {}
                replay["id"] = int(query.value(0))
                replay["name"] = query.value(1)
                replay["map"] = os.path.basename(os.path.splitext(query.value(2))[0])
                replay["start"] = query.value(3).toTime_t()
                replay["end"] = query.value(4).toTime_t()
                replay["duration"] = query.value(4).toTime_t() - query.value(3).toTime_t()
                replay["mod"] = query.value(5)
                replays.append(replay)

            self.sendJSON(dict(command = "replay_vault", action = "list_recents", replays = replays))
        
        
        
    def command_search(self, message):
        mod     = message["mod"]
        mapname = message["map"]
        player  = message["player"]
        rating  = message.get("rating", 0)

        modUid = -1
        mapUid = -1
        
        query = QSqlQuery(self.parent.db)
        query.setForwardOnly(True)

        if mapname != "":
            query.prepare("SELECT id FROM `table_map` WHERE LOWER( `name` ) REGEXP ? LIMIT 1")
            mapname = "^" + mapname.lower().replace("*", ".*") +"$"
            query.addBindValue(mapname)
            query.exec_()
            if query.size() != 0:
                query.first()
                mapUid = int(query.value(0))
            else:
                return
            
        if mod != "All":
            query.prepare("SELECT id FROM `game_featuredMods` WHERE gamemod = ? LIMIT 1")
            query.addBindValue(mod)
            query.exec_()
            if query.size() != 0:
                query.first()
                modUid = int(query.value(0))
            else:
                return

        queryStr = "\
SELECT game_stats.id, game_stats.gameName, table_map.filename, game_stats.startTime, game_stats.EndTime, game_featuredMods.gameMod \
FROM game_stats \
INNER JOIN table_map ON table_map.id = game_stats.mapId \
INNER JOIN game_player_stats ON game_player_stats.gameId = game_stats.id \
INNER JOIN game_featuredMods ON game_featuredMods.id = game_stats.gameMod \
WHERE  (-1 = ? OR game_stats.gameMod = ?) \
AND (mean - 3*deviation) >= ? \
AND (-1 = ? OR mapId = ?) \n"

        if player != "":
            query.prepare("SELECT id from login where LOWER(login) REGEXP ?")
            query.addBindValue(player.lower())
            query.exec_()
            if query.size() > 1:
                players = []
                i = 0
                while query.next() and i < 100:
                    players.append(query.value(0))
                    i += 1
                queryStr += "AND game_player_stats.playerId IN ("+reduce(lambda x, y: str(x)+","+str(y), players)+") "
            elif query.size() == 1:
                query.first()
                playerId = query.value(0)
                queryStr += "AND game_player_stats.playerId = " + str(playerId) + "\n"

        queryStr += "ORDER BY id DESC LIMIT 150"
        query.prepare(queryStr)
        query.addBindValue(modUid)
        query.addBindValue(modUid)
        query.addBindValue(rating)
        query.addBindValue(mapUid)
        query.addBindValue(mapUid)
        
        if not query.exec_():
            self.logger.debug(query.lastQuery())
            self.logger.debug(query.lastError())
            
        if query.size() > 0:
            replays = []
            while query.next():
                replay = {}
                replay["id"] = int(query.value(0))
                replay["name"] = query.value(1)
                replay["map"] = os.path.basename(os.path.splitext(query.value(2))[0])
                replay["start"] = query.value(3).toTime_t()
                replay["end"] = query.value(4).toTime_t()
                replay["duration"] = query.value(4).toTime_t() - query.value(3).toTime_t()
                replay["mod"] = query.value(5)
                replays.append(replay)
            self.sendJSON(dict(command = "replay_vault", action = "search_result", replays = replays))
        else:
            self.logger.debug("Empty search")
            self.logger.debug(query.boundValues())
            self.logger.debug(query.lastQuery())
            self.sendJSON(dict(command = "replay_vault", action = "search_result", replays = []))

                    
        
                
    
    def command_info_replay(self, message):
        uid = message["uid"]
        query = QSqlQuery(self.parent.db)
        query.setForwardOnly(True)
        query.prepare("SELECT login.login, faction, color, team, place, (mean-3*deviation), score, scoreTime \
                        FROM `game_player_stats` \
                        LEFT JOIN login ON login.id = `playerId` \
                        WHERE `gameId` = ?")
        query.addBindValue(uid)
        query.exec_()
        if  query.size() > 0:
            players = []
            while query.next():
                player = {}
                player["name"] = str(query.value(0))   
                player["faction"] = query.value(1)
                player["color"] = query.value(2)
                player["team"] = query.value(3)
                player["place"] = query.value(4)
                if query.value(5):
                    player["rating"] = max(0, int(round((query.value(5))/100.0)*100)) 
                    
#                if query.value(6) :
#                    player["after_rating"] = query.value(6)
                if query.value(6):
                    player["score"] = query.value(6)
    #                    if query.value(8) :
    #                        player["scoreTime"] = query.value(8)
                players.append(player)
            ##self.logger.debug(players)
            self.sendJSON(dict(command = "replay_vault", action = "info_replay", uid = uid, players = players))
        
    
    def handleAction(self, action, stream):
        self.receiveJSON(action, stream)
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
        self.done()

    def sendJSON(self, data_dictionary):
        """
        Simply dumps a dictionary into a string and feeds it into the QTCPSocket
        """
        try:
            data_string = json.dumps(data_dictionary)
        except:

            return

        self.sendReply(data_string)

    def receiveJSON(self, data_string, stream):
        """
        A fairly pythonic way to process received strings as JSON messages.
        """
        message = json.loads(data_string)
        cmd = "command_" + message['command']
        self.logger.debug("handling command : " + cmd)
        if hasattr(self, cmd):
            
            self.lock()
            getattr(self, cmd)(message)
            self.unlock()  


    def sendReply(self, action, *args, **kwargs):
        
        try:
            
            if hasattr(self, "socket"):

                reply = QByteArray()
                stream = QDataStream(reply, QIODevice.WriteOnly)
                stream.setVersion(QDataStream.Qt_4_2)
                stream.writeUInt32(0)
                
                stream.writeQString(action)

    
                for arg in args:
                    if type(arg) is LongType:
                        stream.writeQString(str(arg))
                    if type(arg) is IntType:
                        stream.writeInt(int(arg))
                    elif type(arg) is StringType:
                        stream.writeQString(arg)
                    elif isinstance(arg, str):                       
                        stream.writeQString(arg) 
                    elif type(arg) is FloatType:
                        stream.writeFloat(arg)
                    elif type(arg) is ListType:
                        stream.writeQString(str(arg))                        
                    elif type(arg) is QFile:
                        arg.open(QIODevice.ReadOnly)
                        fileDatas = QByteArray(arg.readAll())
                        stream.writeInt32(fileDatas.size())
                        stream.writeRawData(fileDatas.data())
                        arg.close()                        
                #stream << action << options
                stream.device().seek(0)
                
                stream.writeUInt32(reply.size() - 4)
                self.socket.write(reply)


        except:
                self.logger.exception("Something awful happened when sending reply !")  
  
    def done(self):
        if self.socket is not None:
            #self.parent.addSocketToDelete(self.socket)
            self.socket.readyRead.disconnect(self.readDatas)
            self.socket.disconnected.disconnect(self.disconnection)
            self.socket.error.disconnect(self.displayError)
            self.socket.close()
            #self.socket.deleteLater()
            self.socket = None
        
        self.parent.removeUpdater(self)
        
        
        
    # Display errors from servers
    def displayError(self, socketError):
        if socketError == QtNetwork.QAbstractSocket.RemoteHostClosedError:
            self.logger.warning("RemoteHostClosedError")
     

        elif socketError == QtNetwork.QAbstractSocket.HostNotFoundError:
            self.logger.warning("HostNotFoundError")
        elif socketError == QtNetwork.QAbstractSocket.ConnectionRefusedError:
            self.logger.warning("ConnectionRefusedError")
        else:
            self.logger.warning("The following error occurred: %s." % self.socket.errorString())
