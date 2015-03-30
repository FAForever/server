# -------------------------------------------------------------------------------
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
import hashlib
import zlib
import cgi
import socket
import base64
import json
import urllib.parse
import datetime
import zipfile
import os
import shutil
import random
import re
import time
import logging
import smtplib
from email.mime.text import MIMEText
import email.utils

from PySide.QtCore import QTimer
from PySide.QtCore import QByteArray, QDataStream, QIODevice, QFile, QObject
from PySide import QtNetwork
from PySide.QtSql import QSqlQuery
import pygeoip

from src.decorators import timed
from src.players import *
from passwords import PW_SALT, STEAM_APIKEY, PRIVATE_KEY, decodeUniqueId, MAIL_ADDRESS
from config import Config


gi = pygeoip.GeoIP('GeoIP.dat', pygeoip.MEMORY_CACHE)

FA = 9420
LADDER_SEASON = "ladder_season_5"

from steam import api

api.key.set(STEAM_APIKEY)

from src.games.ladderGamesContainer import Ladder1V1GamesContainer
from src.games.coopGamesContainer import CoopGamesContainer
from src.games.matchmakerGamesContainer import MatchmakerGamesContainer
from src.games.gamesContainer import GamesContainer


TIMEOUT_SECONDS = 300

logger = logging.getLogger(__name__)


class LobbyConnection(QObject):
    @timed()
    def __init__(self, socket, parent=None):
        super(LobbyConnection, self).__init__(parent)
        self.parent = parent

        self.log = logging.getLogger(__name__)

        self.log.debug("Incoming lobby socket started")

        self.season = LADDER_SEASON

        self.socket = socket

        self.socket.disconnected.connect(self.disconnection)
        self.socket.error.connect(self.displayError)
        self.socket.stateChanged.connect(self.stateChange)

        self.ladderPotentialPlayers = []
        self.warned = False

        self.loginDone = False

        self.initTimer = QTimer(self)
        self.initTimer.timeout.connect(self.initNotDone)
        self.initTimer.start(2000)

        if self.socket is not None and self.socket.state() == 3 and self.socket.isValid():
            self.privkey = PRIVATE_KEY

            self.noSocket = False
            self.readingSocket = False

            self.addGameModes()

            self.player = None

            self.initPing = True
            self.ponged = False
            self.steamChecked = False

            self.logPrefix = "\t"

            self.missedPing = 0

            self.nextBlockSize = 0

            self.blockSize = 0

            self.friendList = []
            self.foeList = []
            self.ladderMapList = []

            self.leagueAvatar = None

            self.email = None
            self.uid = None

            self.ip = self.socket.peerAddress().toString()
            self.port = self.socket.peerPort()
            self.peerName = self.socket.peerName()

            self.socket.readyRead.connect(self.readData)

            self.pingTimer = None

            self.session = int(random.getrandbits(16))

        else:
            self.log.warning("We are not connected")
            self.socket.abort()

    @timed()
    def initNotDone(self):
        self.initTimer.stop()
        self.log.warning("Init not done for this IP : " + self.socket.peerAddress().toString())
        if not self.loginDone:
            self.log.warning("aborting socket")
            self.socket.abort()
        try:
            self.socket.readyRead.disconnect(self.readData)
        except:
            pass

    @timed()
    def addGameModes(self):
        if not self.parent.games.isaContainer("faf"):
            self.parent.games.addContainer("faf", GamesContainer("faf", "Forged Alliance Forever", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("ladder1v1"):
            self.parent.games.addContainer("ladder1v1", Ladder1V1GamesContainer(self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("nomads"):
            self.parent.games.addContainer("nomads", GamesContainer("nomads", "The Nomads", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("labwars"):
            self.parent.games.addContainer("labwars",
                                           GamesContainer("labwars", "LABwars", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("murderparty"):
            self.parent.games.addContainer("murderparty",
                                           GamesContainer("murderparty", "Murder Party", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("blackops"):
            self.parent.games.addContainer("blackops",
                                           GamesContainer("blackops", "blackops", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("xtremewars"):
            self.parent.games.addContainer("xtremewars",
                                           GamesContainer("xtremewars", "Xtreme Wars", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("diamond"):
            self.parent.games.addContainer("diamond",
                                           GamesContainer("diamond", "Diamond", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("phantomx"):
            self.parent.games.addContainer("phantomx",
                                           GamesContainer("phantomx", "phantom-X", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("vanilla"):
            self.parent.games.addContainer("vanilla",
                                           GamesContainer("vanilla", "Vanilla", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("civilians"):
            self.parent.games.addContainer("civilians",
                                           GamesContainer("civilians", "Civilians Defense", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("koth"):
            self.parent.games.addContainer("koth", GamesContainer("koth", "King of the Hill", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("claustrophobia"):
            self.parent.games.addContainer("claustrophobia",
                                           GamesContainer("claustrophobia", "Claustrophobia", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("supremedestruction"):
            self.parent.games.addContainer("supremedestruction",
                                           GamesContainer("supremeDestruction", "Supreme Destruction", self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("coop"):
            self.parent.games.addContainer("coop", CoopGamesContainer(self.parent.db, self.parent.games))

        if not self.parent.games.isaContainer("matchmaker"):
            self.parent.games.addContainer("matchmaker",
                                           MatchmakerGamesContainer(self.parent.db, self.parent.games))

    @timed()
    def getRankColor(self, deviation):
        ##self.log.debug(self.logPrefix + "Get rank color")
        normalized = min((deviation / 400.0), 1.0)
        col = int(255 + normalized * (0 - 255))
        ##self.log.debug("Get rank color done")
        return '%02x%02x%02x%02x' % (col, col, col, col)

    @timed()
    def removeLobbySocket(self):
        if self.socket is not None:
            self.socket.abort()

    @timed()
    def ping(self):
        if hasattr(self, "socket"):
            if not self.noSocket:
                # if last ping didn't answer, we can assume that the guy is gone.
                if self.ponged == False and self.initPing == False:
                    if self.missedPing > 2:
                        self.log.debug(
                            self.logPrefix + " Missed 2 ping - Removing user IP " + self.socket.peerAddress().toString())

                        if self in self.parent.recorders:
                            self.removeLobbySocket()

                    else:
                        self.sendReply("PING")
                        self.missedPing += 1
                else:
                    self.sendReply("PING")
                    self.ponged = False
                    self.missedPing = 0

                if self.initPing:
                    self.initPing = False


    @timed()
    def checkOldGamesFromPlayer(self):
        pass


    @timed()
    def joinGame(self, uuid, gamePort, password=None):
        self.checkOldGamesFromPlayer()
        self.parent.games.removeOldGames()

        if gamePort == '' or gamePort == 0 or gamePort is None:
            gamePort = 6112

        game = self.parent.games.find_by_id(uuid)

        if game is not None:
            if game.lobbyState == "open":
                gameExists = True
            else:
                return
        else:
            return

        if gameExists:
            if game.password != password:
                self.sendJSON(dict(command="notice", style="info", text="Bad password (it's case sensitive)"))
                return

            container = self.parent.games.getGameContainer(game)
            mod = container.gameTypeName.lower()

            if self.player is not None:
                self.player.setAction("JOIN")
                self.player.wantToConnectToGame = True
                self.player.setGamePort(gamePort)
                self.player.localGamePort = gamePort
                self.player.setGame(uuid)
            else:
                return

            jsonToSend = {"command": "game_launch", "mod": mod, "uid": uuid}
            if len(game.mods) > 0:
                jsonToSend["sim_mods"] = game.mods
            if len(game.options) != 0:
                jsonToSend["options"] = []
                numOptions = len(container.options)
                if numOptions == len(game.options):
                    jsonToSend["options"] = game.options
                else:
                    for i in range(numOptions):
                        jsonToSend["options"].append(True)

            flags = ["/numgames " + str(self.player.numGames)]
            jsonToSend["args"] = flags

            self.sendJSON(jsonToSend)

    @timed()
    def hostGame(self, access, gameName, gamePort, version, mod="faf", map='SCMP_007', password=None, rating=1,
                 options=[]):
        mod = mod.lower()
        self.checkOldGamesFromPlayer()
        self.parent.games.removeOldGames()

        if not gameName:
            gameName = self.player.login

        if not gamePort:
            gamePort = 6112

        jsonToSend = {}

        game = self.parent.games.create_game(access, mod, self.player, gameName, gamePort, map, password)
        if game:
            uuid = game.uuid

            self.player.setAction("HOST")
            self.player.wantToConnectToGame = True
            self.player.setGame(uuid)
            self.player.setGamePort(gamePort)
            self.player.localGamePort = gamePort

            jsonToSend["command"] = "game_launch"
            jsonToSend["mod"] = mod
            jsonToSend["uid"] = uuid
            jsonToSend["version"] = version

            flags = ["/numgames " + str(self.player.numGames)]
            jsonToSend["args"] = flags

            if len(options) != 0:
                game.options = options
                jsonToSend["options"] = []
                numOptions = len(self.parent.games.getGameContainer(game).options)
                if numOptions == len(options):
                    jsonToSend["options"] = options
                else:
                    for i in range(numOptions):
                        jsonToSend["options"].append(True)

            self.sendJSON(jsonToSend)

        else:
            self.sendJSON(dict(command="notice", style="error", text="You are already hosting a game"))


    @timed()
    def handleAction(self, action, stream):
        try:
            if action == "PING":
                self.sendReply("PONG")

            elif action == "PONG":
                self.ponged = True

            elif action == "UPLOAD_MOD":
                login = stream.readQString()
                session = stream.readQString()

                zipmap = stream.readQString()
                infos = stream.readQString()
                size = stream.readInt32()
                fileDatas = stream.readRawData(size)
                message = json.loads(infos)

                if not 'name' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No mod name provided."))
                    return

                if not 'uid' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No uid provided."))
                    return

                if not 'description' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No description provided."))
                    return

                if not 'author' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No author provided."))
                    return

                if not 'ui_only' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No mod type provided."))
                    return

                if not 'version' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No mod version provided."))
                    return

                name = message["name"]
                name = name.replace("'", "\\'")
                description = message["description"]
                description = description.replace("'", "\\'")

                uid = message["uid"]
                version = message["version"]
                author = message["author"]
                ui = message["ui_only"]
                big = message["big"]
                small = message["small"]
                icon = ""

                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT * FROM table_mod WHERE uid = ?")
                query.addBindValue(uid)
                query.exec_()
                if query.size() != 0:
                    error = name + " uid " + uid + "already exists in the database."
                    self.sendJSON(dict(command="notice", style="error", text=error))
                    return

                query.prepare("SELECT filename FROM table_mod WHERE filename LIKE '%" + zipmap + "%'")
                query.exec_()
                if query.size() == 0:
                    writeFile = QFile(Config['global']['content_path'] + "vault/mods/%s" % zipmap)

                    if writeFile.open(QIODevice.WriteOnly):
                        writeFile.write(fileDatas)
                    writeFile.close()

                    if zipfile.is_zipfile(Config['global']['content_path'] + "vault/mods/%s" % zipmap):
                        zip = zipfile.ZipFile(Config['global']['content_path'] + "vault/mods/%s" % zipmap, "r",
                                              zipfile.ZIP_DEFLATED)

                        if zip.testzip() is None:

                            for member in zip.namelist():
                                #QCoreApplication.processEvents()
                                filename = os.path.basename(member)
                                if not filename:
                                    continue
                                if filename.endswith(".png"):
                                    source = zip.open(member)
                                    target = open(
                                        os.path.join(Config['global']['content_path'] + "vault/mods_thumbs/",
                                                     zipmap.replace(".zip", ".png")), "wb")
                                    icon = zipmap.replace(".zip", ".png")

                                    shutil.copyfileobj(source, target)
                                    source.close()
                                    target.close()

                            #add the datas in the db
                            filename = "mods/%s" % zipmap

                            query = QSqlQuery(self.parent.db)
                            query.prepare(
                                "INSERT INTO `table_mod`(`uid`, `name`, `version`, `author`, `ui`, `big`, `small`, `description`, `filename`, `icon`) VALUES (?,?,?,?,?,?,?,?,?,?)")
                            query.addBindValue(uid)
                            query.addBindValue(name)
                            query.addBindValue(version)
                            query.addBindValue(author)
                            query.addBindValue(int(ui))
                            query.addBindValue(int(big))
                            query.addBindValue(int(small))
                            query.addBindValue(description)
                            query.addBindValue(filename)
                            query.addBindValue(icon)

                            if not query.exec_():
                                self.log.debug(query.lastError())

                        zip.close()

                        self.sendJSON(dict(command="notice", style="info", text="Mod correctly uploaded."))
                    else:
                        self.sendJSON(
                            dict(command="notice", style="error", text="Cannot unzip mod. Upload error ?"))
                else:
                    self.sendJSON(dict(command="notice", style="error",
                                       text="This file (%s) is already in the database !" % str(zipmap)))


            elif action == "UPLOAD_MAP":
                login = stream.readQString()
                session = stream.readQString()

                zipmap = stream.readQString()
                infos = stream.readQString()
                size = stream.readInt32()

                fileDatas = stream.readRawData(size)

                message = json.loads(infos)

                unranked = False

                if not 'name' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No map name provided."))
                    return

                if not 'description' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No map description provided."))
                    return

                if not 'max_players' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No max players provided."))
                    return

                if not 'map_type' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No map type provided."))
                    return

                if not 'battle_type' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No battle type provided."))
                    return

                if not 'map_size' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No map size provided."))
                    return

                if not 'version' in message:
                    self.sendJSON(dict(command="notice", style="error", text="No version provided."))
                    return

                name = message["name"]
                description = message["description"]
                description = description.replace("'", "\\'")

                max_players = message["max_players"]
                map_type = message["map_type"]
                battle_type = message["battle_type"]

                map_size = message["map_size"]
                map_size_X = str(map_size["0"])
                map_size_Y = str(map_size["1"])
                version = message["version"]

                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT * FROM table_map WHERE name = ? and version = ?")
                query.addBindValue(name)
                query.addBindValue(version)
                query.exec_()
                if query.size() != 0:
                    error = name + " version " + version + "already exists in the database."
                    self.sendJSON(dict(command="notice", style="error", text=error))
                    return

                query.prepare("SELECT filename FROM table_map WHERE filename LIKE ?")
                query.addBindValue("%" + zipmap + "%")
                query.exec_()

                if query.size() == 0:
                    writeFile = QFile(Config['global']['content_path'] + "vault/maps/%s" % zipmap)

                    if writeFile.open(QIODevice.WriteOnly):
                        writeFile.write(fileDatas)
                    writeFile.close()

                    if zipfile.is_zipfile(Config['global']['content_path'] + "vault/maps/%s" % zipmap):
                        zip = zipfile.ZipFile(Config['global']['content_path'] + "vault/maps/%s" % zipmap, "r",
                                              zipfile.ZIP_DEFLATED)

                        if zip.testzip() is None:

                            for member in zip.namelist():
                                filename = os.path.basename(member)
                                if not filename:
                                    continue
                                if filename.endswith(".small.png"):
                                    source = zip.open(member)
                                    target = open(
                                        os.path.join(Config['global']['content_path'] + "vault/map_previews/small/",
                                                     filename.replace(".small.png", ".png")), "wb")

                                    shutil.copyfileobj(source, target)
                                    source.close()
                                    target.close()
                                elif filename.endswith(".large.png"):
                                    source = zip.open(member)
                                    target = open(
                                        os.path.join(Config['global']['content_path'] + "vault/map_previews/large/",
                                                     filename.replace(".large.png", ".png")), "wb")

                                    shutil.copyfileobj(source, target)
                                    source.close()
                                    target.close()
                                elif filename.endswith("_script.lua"):
                                    fopen = zip.open(member)
                                    temp = []
                                    for line in fopen:
                                        temp.append(line.rstrip())
                                        text = " ".join(temp)

                                    pattern = re.compile("function OnPopulate\(\)(.*?)end")
                                    match = re.search(pattern, text)
                                    if match:
                                        script = match.group(1).replace("ScenarioUtils.InitializeArmies()",
                                                                        "").replace(" ", "").strip()
                                        if len(script) > 0:
                                            if len(script.lower().replace(" ", "").replace(
                                                    "scenarioframework.setplayablearea('area_1',false)",
                                                    "").strip()) > 0:
                                                unranked = True
                                    fopen.close()



                            # check if the map name is already there
                            gmuid = 0
                            query = QSqlQuery(self.parent.db)
                            query.prepare("SELECT mapuid FROM table_map WHERE name = ?")
                            query.addBindValue(name)
                            query.exec_()
                            if query.size() != 0:
                                query.first()
                                gmuid = int(query.value(0))

                            else:
                                query = QSqlQuery(self.parent.db)
                                query.prepare("SELECT MAX(mapuid) FROM table_map")
                                query.exec_()
                                if query.size() != 0:
                                    query.first()
                                    gmuid = int(query.value(0)) + 1

                            #add the data in the db
                            filename = "maps/%s" % zipmap

                            query = QSqlQuery(self.parent.db)
                            query.prepare(
                                "INSERT INTO table_map(name,description,max_players,map_type,battle_type,map_sizeX,map_sizeY,version,filename, mapuid) VALUES (?,?,?,?,?,?,?,?,?,?)")
                            query.addBindValue(name)
                            query.addBindValue(description)
                            query.addBindValue(max_players)
                            query.addBindValue(map_type)
                            query.addBindValue(battle_type)
                            query.addBindValue(map_size_X)
                            query.addBindValue(map_size_Y)
                            query.addBindValue(version)
                            query.addBindValue(filename)
                            query.addBindValue(gmuid)

                            if not query.exec_():
                                self.log.debug(query.lastError())

                            uuid = query.lastInsertId()

                            query.prepare("INSERT INTO `table_map_uploaders`(`mapid`, `userid`) VALUES (?,?)")
                            query.addBindValue(uuid)
                            query.addBindValue(self.player.id)
                            if not query.exec_():
                                self.log.debug(query.lastError())

                            if unranked:
                                query.prepare("INSERT INTO `table_map_unranked`(`id`) VALUES (?)")
                                query.addBindValue(uuid)
                                if not query.exec_():
                                    self.log.debug(query.lastError())

                        zip.close()

                        self.sendJSON(dict(command="notice", style="info", text="Map correctly uploaded."))
                    else:
                        self.sendJSON(
                            dict(command="notice", style="error", text="Cannot unzip map. Upload error ?"))
                else:
                    self.sendJSON(
                        dict(command="notice", style="error", text="This map is already in the database !"))

            elif action == "CREATE_ACCOUNT":
                login = stream.readQString()
                em = stream.readQString()
                password = stream.readQString()

                username_pattern = re.compile(r"^[^,]{1,20}$")
                email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}$")
                if not email_pattern.match(em):
                    self.sendJSON(dict(command="notice", style="info",
                                       text="Please use a valid email address."))
                    self.sendReply("LOGIN_AVAILABLE", "no", login)
                    return

                if not username_pattern.match(login):
                    self.sendJSON(dict(command="notice", style="info",
                                       text="Please don't use \",\" in your username."))
                    self.sendReply("LOGIN_AVAILABLE", "no", login)
                    return

                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT id FROM `login` WHERE LOWER(`login`) = ?")
                query.addBindValue(login.lower())
                if not query.exec_():
                    self.log.debug("Error inserting login %s", login)
                    self.log.debug(query.lastError())
                    self.sendReply("LOGIN_AVAILABLE", "no", login)
                    return

                if query.size() != 0:
                    self.log.debug("Login not available: %s", login)
                    self.sendReply("LOGIN_AVAILABLE", "no", login)
                    return

                query.prepare("INSERT INTO login (login, password, email) VALUES (?,?,?)")
                query.addBindValue(login)
                query.addBindValue(password)
                query.addBindValue(em)

                if not query.exec_():
                    self.log.debug("Error inserting login %s", login)
                    self.log.debug(query.lastError())
                    self.sendReply("LOGIN_AVAILABLE", "no", login)
                    return

                uid = query.lastInsertId()

                exp = time.strftime("%Y-%m-%d %H:%m:%S", time.gmtime())
                key = hashlib.md5()
                key.update(login + '_' + em + str(random.randrange(0, 10000)) + exp + PW_SALT)
                keyHex = key.hexdigest()
                query.prepare("INSERT INTO `validate_account` (`UserID`,`Key`,`expDate`) VALUES (?,?,?)")
                query.addBindValue(uid)
                query.addBindValue(keyHex)
                query.addBindValue(exp)
                query.exec_()
                self.log.debug("Sending registration mail")
                link = {'a': 'validate', 'email': keyHex, 'u': base64.b64encode(str(uid))}
                passwordLink = Config['global']['app_url'] + "validateAccount.php?" + urllib.parse.urlencode(link)

                text = "Dear " + login + ",\n\n\
Please visit the following link to validate your FAF account:\n\
-----------------------\n\
" + passwordLink + "\n\
-----------------------\n\\n\
Thanks,\n\
-- The FA Forever team"

                msg = MIMEText(text)

                msg['Subject'] = 'Forged Alliance Forever - Account validation'
                msg['From'] = email.utils.formataddr(('Forged Alliance Forever', MAIL_ADDRESS))
                msg['To'] = email.utils.formataddr((login, em))

                self.log.debug("sending mail to " + em)
                #self.log.debug(msg.as_string())
                #s = smtplib.SMTP(config['global']['smtp_server'])
                s = smtplib.SMTP_SSL(Config['global']['smtp_server'], 465, Config['global']['smtp_server'],
                                     timeout=5)
                s.login(Config['global']['smtp_username'], Config['global']['smtp_password'])

                s.sendmail(MAIL_ADDRESS, [em], msg.as_string())
                s.quit()

                self.sendJSON(dict(command="notice", style="info",
                                   text="A e-mail has been sent with the instructions to validate your account"))
                self.log.debug("sent mail")
                self.sendReply("LOGIN_AVAILABLE", "yes", login)
            elif action == "FA_CLOSED":
                login = stream.readQString()
                session = stream.readQString()
                self.player.setAction("NOTHING")
                self.player.gameThread.abort()
            else:
                login = stream.readQString()
                session = stream.readQString()
                self.receiveJSON(action, stream)
        except:
            self.log.exception("Something awful happened in a lobby thread !")


    @timed()
    def readData(self):
        packetSize = 0
        if self.initTimer:
            packetSize = self.socket.bytesAvailable()
            if packetSize > 120:
                self.log.warning("invalid handshake ! - Packet too big (" + str(
                    packetSize) + " ) " + self.socket.peerAddress().toString())
                self.socket.abort()
                return

        if self.noSocket == False and self.socket.isValid():

            if self.socket.bytesAvailable() == 0:
                self.socket.abort()
                return

            ins = QDataStream(self.socket)

            ins.setVersion(QDataStream.Qt_4_2)
            while not ins.atEnd():

                if self.noSocket == False and self.socket.isValid():

                    if self.blockSize == 0:
                        if self.noSocket == False and self.socket.isValid():
                            if self.socket.bytesAvailable() < 4:
                                if self.initTimer:
                                    self.log.warning(
                                        "invalid handshake ! - no valid packet size " + self.socket.peerAddress().toString())
                                    self.socket.abort()
                                    return

                                return

                            self.blockSize = ins.readUInt32()
                            if self.initTimer:
                                if (packetSize - 4) != self.blockSize:
                                    self.log.warning(
                                        "invalid handshake ! - packet not fit ! " + self.socket.peerAddress().toString())
                                    self.socket.abort()
                                    return

                        else:
                            self.socket.abort()
                            return

                    if self.noSocket == False and self.socket.isValid():
                        if self.socket.bytesAvailable() < self.blockSize:
                            bytesReceived = str(self.socket.bytesAvailable())
                            self.sendReply("ACK", bytesReceived)

                            return

                        bytesReceived = str(self.socket.bytesAvailable())
                        self.sendReply("ACK", bytesReceived)


                    else:
                        self.socket.abort()
                        return

                    action = ins.readQString()
                    self.handleAction(action, ins)

                    self.blockSize = 0

                else:
                    self.socket.abort()
                    return
            return


    @timed()
    def disconnection(self):
        self.noSocket = True
        self.done()

    @timed()
    def getPlayerTournament(self, player):
        tojoin = []
        for container in self.parent.games.gamesContainer:

            if self.parent.games.gamesContainer[container].type == 1:
                for tournament in self.parent.games.gamesContainer[container].getTournaments():
                    if tournament.state == "playing":
                        if player.getLogin() in tournament.players:
                            tojoin.append("#" + tournament.name.replace(" ", "_"))
                        elif player.getLogin() == tournament.host:
                            tojoin.append("#" + tournament.name.replace(" ", "_"))

        return tojoin

    @timed()
    def sendReplaySection(self):
        reply = QByteArray()

        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT `section`,`description` FROM `tutorial_sections`")
        query.exec_()
        if query.size() > 0:
            while query.next():
                jsonToSend = {"command": "tutorials_info", "section": query.value(0), "description": query.value(1)}
                reply.append(self.prepareBigJSON(jsonToSend))

        query.prepare(
            "SELECT tutorial_sections.`section`,`name`,`url`, `tutorials`.`description`, `map` FROM `tutorials` LEFT JOIN  tutorial_sections ON tutorial_sections.id = tutorials.section ORDER BY `tutorials`.`section`, name")
        query.exec_()
        if query.size() > 0:
            while query.next():
                jsonToSend = {"command": "tutorials_info", "tutorial": query.value(1), "url": query.value(2),
                              "tutorial_section": query.value(0), "description": query.value(3),
                              "mapname": query.value(4)}
                reply.append(self.prepareBigJSON(jsonToSend))

        self.sendArray(reply)

    @timed()
    def sendCoopList(self):
        reply = QByteArray()

        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT name, description, filename, type, id FROM `coop_map`")
        query.exec_()
        if query.size() > 0:
            while query.next():
                jsonToSend = {"command": "coop_info", "name": query.value(0), "description": query.value(1),
                              "filename": query.value(2), "featured_mod": "coop"}
                if query.value(3) == 0:
                    jsonToSend["type"] = "FA Campaign"
                elif query.value(3) == 1:
                    jsonToSend["type"] = "Aeon Vanilla Campaign"
                elif query.value(3) == 2:
                    jsonToSend["type"] = "Cybran Vanilla Campaign"
                elif query.value(3) == 3:
                    jsonToSend["type"] = "UEF Vanilla Campaign"

                else:
                    jsonToSend["type"] = "Unknown"
                jsonToSend["uid"] = query.value(4)
                reply.append(self.prepareBigJSON(jsonToSend))

        self.sendArray(reply)

    @timed()
    def sendModList(self):
        reply = QByteArray()

        for containerName in self.parent.games.gamesContainer:

            container = self.parent.games.gamesContainer[containerName]

            jsonToSend = {
                "command": "mod_info",
                "name": container.gameTypeName,
                "fullname": container.gameNiceName,
                "icon": None,
                "host": container.host,
                "join": container.join,
                "live": container.live,
                "desc": container.desc,
                "options": container.options
            }

            reply.append(self.prepareBigJSON(jsonToSend))

        self.sendArray(reply)

    @timed()
    def jsonTourney(self, tourney):
        jsonToSend = {"command": "tournament_info", "type": tourney.type, "state": tourney.getState(),
                      "uid": tourney.getid(), "title": tourney.getName(), "host": tourney.host,
                      "min_players": tourney.minPlayers, "max_players": tourney.maxPlayers,
                      "min_rating": tourney.minRating, "max_rating": tourney.maxRating,
                      "description": tourney.description, "players": tourney.seededplayers, "date": tourney.date}
        if tourney.state != "open":
            jsonToSend["action"] = "brackets"
            jsonToSend["result"] = tourney.getDisplayInfos()

        return jsonToSend

    @timed()
    def sendGameList(self):

        reply = QByteArray()

        for key, container in self.parent.games.gamesContainer:
            self.log.debug("sending games of container " + container.gameNiceName)
            if container.listable or container.live:
                for game in container.games:

                    if game.lobbyState == "open" or game.lobbyState == "playing":
                        reply.append(self.prepareBigJSON(self.parent.jsonGame(game)))

            self.log.debug("done")

        self.sendArray(reply)

    @timed()
    def preparePacket(self, action, *args, **kwargs):

        reply = QByteArray()
        stream = QDataStream(reply, QIODevice.WriteOnly)
        stream.setVersion(QDataStream.Qt_4_2)
        stream.writeUInt32(0)

        stream.writeQString(action)

        for arg in args:
            if isinstance(arg, int):
                stream.writeInt32(arg)
            elif isinstance(arg, float):
                stream.writeQString(str(arg))
            elif isinstance(arg, str):
                stream.writeFloat(arg)

        stream.device().seek(0)

        stream.writeUInt32(reply.size() - 4)

        return reply

    @timed()
    def sendArray(self, array):

        if self in self.parent.recorders:
            if not self.noSocket:
                if self.socket.bytesToWrite() > 16 * 1024 * 1024:
                    return

            if self.socket.isValid() and self.socket.state() == 3:

                if self.socket.write(array) == -1:
                    self.noSocket = True
                    self.socket.abort()
            else:
                self.socket.abort()


    @timed()
    def sendReply(self, action, *args, **kwargs):
        if self in self.parent.recorders:
            if not self.noSocket:

                reply = QByteArray()
                stream = QDataStream(reply, QIODevice.WriteOnly)
                stream.setVersion(QDataStream.Qt_4_2)
                stream.writeUInt32(0)

                stream.writeQString(action)

                for arg in args:
                    if isinstance(arg, int):
                        stream.writeInt(arg)
                    elif isinstance(arg, str):
                        stream.writeQString(arg)

                stream.device().seek(0)

                stream.writeUInt32(reply.size() - 4)

                if self.socket.isValid() and self.socket.state() == 3:

                    if self.socket.write(reply) == -1:
                        self.log.debug("error socket write")
                        self.socket.abort()
                        self.noSocket = True
                else:
                    self.socket.abort()

    def command_fa_state(self, message):
        state = message["state"]
        if state == "on":
            if self.player.getAction() == "NOTHING":
                self.player.setAction("FA_LAUNCHED")
            pass
        else:
            self.player.setAction("NOTHING")

    def command_ladder_maps(self, message):
        maplist = message['maps']
        toAdd = set(maplist) - set(self.ladderMapList)
        if len(toAdd) > 0:
            for uid in toAdd:
                query = QSqlQuery(self.parent.db)
                query.prepare("INSERT INTO ladder_map_selection (idUser, idMap) values (?,?)")
                query.addBindValue(self.uid)
                query.addBindValue(uid)
                if not query.exec_():
                    self.log.debug(query.lastError())

        toRemove = set(self.ladderMapList) - set(maplist)
        if len(toRemove) > 0:
            for uid in toRemove:
                query = QSqlQuery(self.parent.db)
                query.prepare("DELETE FROM ladder_map_selection WHERE idUser = ? and idMap = ?")
                query.addBindValue(self.uid)
                query.addBindValue(uid)
                if not query.exec_():
                    self.log.debug(query.lastError())

        self.ladderMapList = maplist


    def command_quit_team(self, message):
        """We want to quit our team"""
        #inform all members
        leader = self.parent.teams.getSquadLeader(self.player.getLogin())
        if not leader:
            return
        members = self.parent.teams.getAllMembers(leader)

        if leader == self.player.getLogin():
            self.parent.teams.disbandSquad(leader)

            for member in members:
                player = self.parent.listUsers.findByName(member)
                if player:
                    player.lobbyThread.sendJSON(dict(command="team_info", leader="", members=[]))

        else:
            self.parent.teams.removeFromSquad(leader, self.player.getLogin())

            newmembers = self.parent.teams.getAllMembers(leader)

            if len(newmembers) == 1:
                self.parent.teams.disbandSquad(leader)

            for member in members:
                player = self.parent.listUsers.findByName(member)
                if player:
                    player.lobbyThread.sendJSON(dict(command="team_info", leader=leader, members=newmembers))


    def command_accept_team_proposal(self, message):
        """we have accepted a team proposal"""
        leader = message["leader"]

        # first, check if the leader is in a squad...
        if self.parent.teams.isInSquad(leader):
            # if so, check if he is the leader already
            if not self.parent.teams.isLeader(leader):
                #if he is not a leader, we can't accept.
                self.sendJSON(dict(command="notice", style="info",
                                   text="You are already in a team. You can't join another team."))
                return

        squadMembers = self.parent.teams.getAllMembers(leader)
        # check if the squad has place left
        if len(squadMembers) >= 4:
            self.sendJSON(dict(command="notice", style="info", text="Sorry, the team is full."))
            return

        if self.parent.teams.addInSquad(leader, self.player.getLogin()):

            # success, we can inform all the squad members
            members = self.parent.teams.getAllMembers(leader)
            for member in members:
                player = self.parent.listUsers.findByName(member)
                if player:
                    player.lobbyThread.sendJSON(dict(command="team_info", leader=leader, members=members))

    @timed()
    def command_social(self, message):

        if "teaminvite" in message:
            who = message['teaminvite']
            player = self.parent.listUsers.findByName(who)
            if player:
                if self.parent.teams.isInSquad(self.player.getLogin()):
                    self.sendJSON(dict(command="notice", style="info", text="The player is already in a team."))
                    return
                if player.getLogin() != self.player.getLogin():
                    player.lobbyThread.sendJSON(
                        dict(command="team", action="teaminvitation", who=self.player.getLogin()))

        if "friends" in message:
            friendlist = message['friends']
            toAdd = set(friendlist) - set(self.friendList)

            if len(toAdd) > 0:

                for friend in toAdd:
                    query = QSqlQuery(self.parent.db)
                    query.prepare(
                        "INSERT INTO friends (idUser, idFriend) values (?,(SELECT id FROM login WHERE login.login = ?))")
                    query.addBindValue(self.uid)
                    query.addBindValue(friend)
                    query.exec_()

            toRemove = set(self.friendList) - set(friendlist)

            if len(toRemove) > 0:
                for friend in toRemove:
                    query = QSqlQuery(self.parent.db)
                    query.prepare(
                        "DELETE FROM friends WHERE idFriend = (SELECT id FROM login WHERE login.login = ?) AND idUser = ?")
                    query.addBindValue(friend)
                    query.addBindValue(self.uid)
                    query.exec_()

            self.friendList = friendlist

        if "foes" in message:
            foelist = message['foes']
            toAdd = set(foelist) - set(self.foeList)

            if len(toAdd) > 0:

                for foe in toAdd:
                    query = QSqlQuery(self.parent.db)
                    query.prepare(
                        "INSERT INTO foes (idUser, idFoe) values (?,(SELECT id FROM login WHERE login.login = ?))")
                    query.addBindValue(self.uid)
                    query.addBindValue(foe)
                    query.exec_()

            toRemove = set(self.foeList) - set(foelist)

            if len(toRemove) > 0:
                for foe in toRemove:
                    query = QSqlQuery(self.parent.db)
                    query.prepare(
                        "DELETE FROM foes WHERE idFoe = (SELECT id FROM login WHERE login.login = ?) AND idUser = ?")
                    query.addBindValue(foe)
                    query.addBindValue(self.uid)
                    query.exec_()

            self.foeList = foelist


    @timed()
    def resendMail(self, login):
        #self.log.debug("resending mail")       
        query = QSqlQuery(self.parent.db)

        query.prepare(
            "SELECT login.id, login, email, `validate_account`.Key FROM `validate_account` LEFT JOIN login ON `validate_account`.`UserID` = login.id WHERE login = ?")
        query.addBindValue(login)

        query.exec_()
        if query.size() == 1:
            query.first()

            uid = str(query.value(0))
            em = str(query.value(2))
            key = str(query.value(3))

            link = {'a': 'validate', 'email': key, 'u': base64.b64encode(str(uid))}
            passwordLink = Config['global']['app_url'] + "validateAccount.php?" + urllib.parse.urlencode(link)
            text = "Dear " + login + ",\n\n\
Please visit the following link to validate your FAF account:\n\
-----------------------\n\
" + passwordLink + "\n\
-----------------------\n\\n\
Thanks,\n\
-- The FA Forever team"

            msg = MIMEText(str(text))

            msg['Subject'] = 'Forged Alliance Forever - Account validation'
            msg['From'] = email.utils.formataddr(('Forged Alliance Forever', MAIL_ADDRESS))
            msg['To'] = email.utils.formataddr((login, em))

            #self.log.debug("sending SMTP mail to " + em)
            #self.log.debug(msg.as_string())
            #s = smtplib.SMTP(config['global']['smtp_server'])
            s = smtplib.SMTP_SSL(Config['global']['smtp_server'], 465, Config['global']['smtp_server'], timeout=5)
            s.login(Config['global']['smtp_username'], Config['global']['smtp_password'])
            s.sendmail(MAIL_ADDRESS, [em], msg.as_string())
            s.quit()
            self.sendJSON(dict(command="notice", style="info",
                               text="A e-mail has been sent with the instructions to validate your account"))
            #self.log.debug(self.logPrefix + "SMTP resend done")

    @timed()
    def command_admin(self, message):
        action = message['action']

        if action == "closeFA" and self.player.admin:
            who = message['user']

            player = self.parent.listUsers.findByName(who)
            if player:
                player.lobbyThread.sendJSON(dict(command="notice", style="info",
                                   text="Your game was closed by an administrator ({admin_name})."
                                        + "Please refer to our rules for the lobby/game here {rule_link}."
                                   .format(admin_name=self.player.login,
                                           rule_link=Config['lobbyconnection']['rule_link'])))
                player.lobbyThread.sendJSON(dict(command="notice", style="kill"))

        elif action == "join_channel" and self.player.mod:
            whos = message['users']
            channel = message['channel']

            for who in whos:
                player = self.parent.listUsers.findByName(who)
                if player:
                    player.lobbyThread.sendJSON(dict(command="social", autojoin=[channel]))

        elif action == "closelobby" and self.player.admin:
            who = message['user']

            player = self.parent.listUsers.findByName(who)
            if player:
                player.lobbyThread.sendJSON(dict(command="notice", style="info",
                                   text="Your client was closed by an administrator ({admin_name})."
                                        + "Please refer to our rules for the lobby/game here {rule_link}."
                                   .format(admin_name=self.player.login,
                                           rule_link=Config['lobbyconnection']['rule_link'])))
                player.lobbyThread.sendJSON(dict(command="notice", style="kick"))
                player.lobbyThread.socket.abort()

        elif action == "requestavatars" and self.player.admin:
            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT url, tooltip FROM `avatars_list`")
            query.exec_()
            if query.size() > 0:
                avatarList = []
                while query.next():
                    avatar = {"url": str(query.value(0)), "tooltip": str(query.value(1))}
                    avatarList.append(avatar)

                jsonToSend = {"command": "admin", "avatarlist": avatarList}
                self.sendJSON(jsonToSend)

        elif action == "remove_avatar" and self.player.admin:
            idavatar = message["idavatar"]
            iduser = message["iduser"]
            query = QSqlQuery(self.parent.db)
            query.prepare("DELETE FROM `avatars` WHERE `idUser` = ? AND `idAvatar` = ?")
            query.addBindValue(iduser)
            query.addBindValue(idavatar)
            query.exec_()


        elif action == "list_avatar_users" and self.player.admin:
            avatar = message['avatar']
            if avatar is not None:
                query = QSqlQuery(self.parent.db)
                query.prepare(
                    "SELECT `idUser`, `login`, `idAvatar` FROM `avatars` LEFT JOIN `login` ON `login`.`id` = `idUser`  WHERE `idAvatar` = (SELECT id FROM avatars_list WHERE avatars_list.url = ?)")
                query.addBindValue(avatar)
                query.exec_()
                if query.size() > 0:
                    avatarList = []
                    while query.next():
                        avatar = {"iduser": str(query.value(0)), "login": str(query.value(1))}
                        avatarid = query.value(2)
                        avatarList.append(avatar)

            jsonToSend = {"command": "admin", "player_avatar_list": avatarList, "avatar_id": avatarid}
            self.sendJSON(jsonToSend)



        elif action == "add_avatar" and self.player.admin:
            who = message['user']
            avatar = message['avatar']

            query = QSqlQuery(self.parent.db)
            if avatar is None:
                query.prepare(
                    "DELETE FROM `avatars` WHERE `idUser` = (SELECT `id` FROM `login` WHERE `login`.`login` = ?)")
                query.addBindValue(who)
                query.exec_()
            else:
                query.prepare(
                    "INSERT INTO `avatars`(`idUser`, `idAvatar`) VALUES ((SELECT id FROM login WHERE login.login = ?),(SELECT id FROM avatars_list WHERE avatars_list.url = ?)) ON DUPLICATE KEY UPDATE `idAvatar` = (SELECT id FROM avatars_list WHERE avatars_list.url = ?)")
                query.addBindValue(who)
                query.addBindValue(avatar)
                query.addBindValue(avatar)
                query.exec_()

    @timed()
    def command_hello(self, message):
        try:
            version = message['version']
            login = message['login'].strip()
            password = message['password']
            uniqueIdCoded = message['unique_id']
            uniqueId = None
            oldsession = message.get('session', None)

            try:
                uniqueId = decodeUniqueId(self, uniqueIdCoded, login)
            except:
                self.sendJSON(
                    dict(command="notice", style="error", text="We are not able to log you. Try updating your lobby."))
                self.log.info(self.logPrefix + "unable to decypher !!")

            query = QSqlQuery(self.parent.db)
            queryStr = "SELECT version, file FROM version_lobby ORDER BY id DESC LIMIT 1"
            query.exec_(queryStr)

            if query.size() == 1:
                query.first()
                versionDB = query.value(0)
                file = query.value(1)

                # Version of zero represents a developer build.
                if version < versionDB and version != 0:
                    self.sendJSON(dict(command="welcome", update=file))
                    return

            self.logPrefix = login + "\t"

            channels = []
            query = QSqlQuery(self.parent.db)

            # TODO: Hash passwords server-side so the hashing actually *does* something.
            query.prepare(
                "SELECT id, validated, email, steamchecked, session FROM login WHERE login = ? AND password = ?")
            query.addBindValue(login)
            query.addBindValue(password)
            query.exec_()

            if query.size() != 1:
                self.sendJSON(dict(command="notice", style="error",
                                   text="Login not found or password incorrect. They are case sensitive."))
                return

            query.first()

            self.uid = int(query.value(0))
            validated = query.value(1)
            self.email = str(query.value(2))
            self.steamChecked = int(query.value(3))
            session = int(query.value(4))

            if validated == 0:
                reason = "Your account is not validated. Please visit <a href='" + Config['global'][
                    'app_url'] + "faf/validateAccount.php'>" + Config['global'][
                             'app_url'] + "faf/validateAccount.php</a>.<br>Please re-create an account if your email is not correct (<b>" + str(
                    self.email) + "</b>)"
                self.resendMail(login)
                self.sendJSON(dict(command="notice", style="error", text=reason))
                return

            if session != 0:
                #remove ghost
                for p in self.parent.listUsers.players:
                    if p.getLogin() == login:
                        if p.lobbyThread.socket:
                            p.lobbyThread.socket.abort()
                        if p in self.parent.listUsers.players:
                            self.parent.listUsers.players.remove(p)

                for p in self.parent.listUsers.logins:
                    if p == login:
                        self.parent.listUsers.players.remove(p)

                if session == oldsession:
                    self.session = oldsession
                else:
                    query2 = QSqlQuery(self.parent.db)
                    query2.prepare("UPDATE login SET session = ? WHERE id = ?")
                    query2.addBindValue(session)
                    query2.addBindValue(int(self.uid))
                    query2.exec_()

            query.prepare("SELECT reason FROM lobby_ban WHERE idUser = ?")
            query.addBindValue(self.uid)
            query.exec_()
            if query.size() == 1:
                query.first()
                reason = "You are banned from FAF.\n Reason :\n " + query.value(0)
                self.sendJSON(dict(command="notice", style="error", text=reason))
                return

            if not self.steamChecked:
                if uniqueId is None:
                    self.sendJSON(dict(command="notice", style="error",
                                       text="Unique Id found for another user.<br>Multiple accounts are not allowed.<br><br>Try SteamLink: <a href='" +
                                            Config['global']['app_url'] + "faf/steam.php'>" + Config['global'][
                                                'app_url'] + "faf/steam.php</a>"))
                    return
                    # the user is not steam Checked.
                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT uniqueid FROM steam_uniqueid WHERE uniqueId = ?")
                query.addBindValue(uniqueId)
                query.exec_()
                if query.size() > 0:
                    self.sendJSON(dict(command="notice", style="error",
                                       text="This computer has been used by a steam account.<br>You have to authentify your account on steam too in order to use it on this computer :<br>SteamLink: <a href='" +
                                            Config['global']['app_url'] + "faf/steam.php'>" + Config['global'][
                                                'app_url'] + "faf/steam.php</a>"))
                    return

                # check for another account using the same uniqueId as us.
                query = QSqlQuery(self.parent.db)
                query.prepare("SELECT id, login FROM login WHERE uniqueId = ? AND id != ?")
                query.addBindValue(uniqueId)
                query.addBindValue(self.uid)
                query.exec_()

                if query.size() == 1:
                    query.first()

                    idFound = int(query.value(0))
                    otherName = str(query.value(1))

                    self.log.debug("%i (%s) is a smurf of %s" % (self.uid, login, otherName))
                    self.sendJSON(dict(command="notice", style="error",
                                       text="This computer is tied to this account : %s.<br>Multiple accounts are not allowed.<br>You can free this computer by logging in with that account (%s) on another computer.<br><br>Or Try SteamLink: <a href='" +
                                            Config['global']['app_url'] + "faf/steam.php'>" +
                                            Config['global']['app_url'] + "faf/steam.php</a>" % (
                                           otherName, otherName)))

                    query2 = QSqlQuery(self.parent.db)
                    query2.prepare("INSERT INTO `smurf_table`(`origId`, `smurfId`) VALUES (?,?)")
                    query2.addBindValue(self.uid)
                    query2.addBindValue(idFound)
                    query2.exec_()
                    return

                query = QSqlQuery(self.parent.db)
                query.prepare("UPDATE login SET ip = ?, uniqueId = ?, session = ? WHERE id = ?")
                query.addBindValue(self.ip)
                query.addBindValue(str(uniqueId))
                query.addBindValue(self.session)
                query.addBindValue(self.uid)
                query.exec_()
            else:
                # the user is steamchecked
                query = QSqlQuery(self.parent.db)
                query.prepare("UPDATE login SET ip = ?, session = ? WHERE id = ?")
                query.addBindValue(self.ip)
                query.addBindValue(self.session)
                query.addBindValue(self.uid)
                query.exec_()

                query = QSqlQuery(self.parent.db)
                query.prepare("INSERT INTO `steam_uniqueid`(`uniqueid`) VALUES (?)")
                query.addBindValue(str(uniqueId))
                query.exec_()

            query = QSqlQuery(self.parent.db)
            query.prepare("UPDATE anope.anope_db_NickCore SET pass = ? WHERE display = ?")
            m = hashlib.md5()
            m.update(password.encode())
            passwordmd5 = m.hexdigest()
            m = hashlib.md5()
            # Since the password is hashed on the client, what we get at this point is really
            # md5(md5(sha256(password))). This is entirely insane.
            m.update(passwordmd5.encode())
            query.addBindValue("md5:" + str(m.hexdigest()))
            query.addBindValue(login)
            if not query.exec_():
                self.log.error(query.lastError())

            self.player = Player(str(login),
                                 self.session,
                                 self.ip,
                                 self.port,
                                 self.uid,
                                 self)
            self.player.lobbyVersion = version
            self.player.resolvedAddress = self.player.getIp()

            self.player.faction = random.randint(1, 4)

            try:
                hostname = socket.getfqdn(self.player.getIp())
                try:
                    socket.gethostbyname(hostname)
                    self.player.resolvedAddress = self.player.getIp()
                except:
                    self.player.resolvedAddress = self.player.getIp()

            except:
                self.player.resolvedAddress = self.player.getIp()

            ## Clan informations
            query = QSqlQuery(self.parent.db)
            query.prepare(
                "SELECT `clan_tag` FROM `fafclans`.`clan_tags` LEFT JOIN `fafclans`.players_list ON `fafclans`.players_list.player_id = `fafclans`.`clan_tags`.player_id WHERE `faf_id` = ?")
            query.addBindValue(self.uid)
            if not query.exec_():
                self.log.warning(query.lastError())
            if query.size() > 0:
                query.first()
                self.player.clan = str(query.value(0))


            ## ADMIN
            ## --------------------
            self.player.admin = False
            self.player.mod = False
            query.prepare("SELECT `group` FROM `lobby_admin` WHERE `user_id` = ?")
            query.addBindValue(self.uid)
            query.exec_()

            if query.size() > 0:
                query.first()
                # 2 for admins, 1 for mods.
                permissionGroup = query.value(0)

                if permissionGroup >= 2:
                    self.player.admin = True
                if permissionGroup >= 1:
                    self.player.mod = True

                self.sendJSON({"command": "social", "power": permissionGroup})

            ## Country
            ## ----------

            country = gi.country_name_by_addr(self.socket.peerAddress().toString())
            if country is not None:
                self.player.country = str(country)


            ## LADDER LEAGUES ICONS
            ## ----------------------
            # If a user is top of their division or league, set their avatar appropriately.
            #

            # Query to extract the user's league and divison info.
            # Naming a column `limit` was unwise.
            query.prepare(
            "SELECT\
              score,\
              ladder_division.league,\
              ladder_division.name AS division,\
              ladder_division.limit AS `limit`\
            FROM\
              %s,\
              ladder_division\
            WHERE\
              %s.idUser = ? AND\
              %s.league = ladder_division.league AND\
              ladder_division.limit >= %s.score\
            ORDER BY ladder_division.limit ASC\
            LIMIT 1;" % (self.season, self.season, self.season, self.season))
            query.addBindValue(self.player.id)
            query.exec_()
            if query.size() > 0:
                query.first()
                score = float(query.value(0))
                league = int(query.value(1))
                self.player.league = league
                self.player.division = str(query.value(2))
                limit = int(query.value(3))

                cancontinue = True
                if league == 1 and score == 0:
                    cancontinue = False

                if cancontinue:
                    # check if top of the division :
                    query.prepare(
                        "SELECT score, idUser FROM %s WHERE score <= ? and league = ? ORDER BY score DESC" % self.season)
                    query.addBindValue(limit)
                    query.addBindValue(league)
                    #query.addBindValue(self.player.getId())
                    query.exec_()

                    if query.size() >= 4:
                        query.first()
                        for i in range(1, 4):

                            score = float(query.value(0))
                            idUser = int(query.value(1))

                            if idUser != self.player.id or score <= 0:
                                query.next()
                                continue

                            avatar = {
                                "url": str(Config['global']['content_url'] + "avatars/div" + str(i) + ".png")
                            }
                            if i == 1:
                                avatar.tooltip = "First in my division!"
                            elif i == 2:
                                avatar.tooltip = "Second in my division!"
                            elif i == 3:
                                avatar.tooltip = "Third in my division!"

                            self.player.avatar = avatar
                            self.leagueAvatar = avatar

                            break

                    # check if top of the league :
                    query.prepare(
                        "SELECT score, idUser FROM %s  WHERE league = ? ORDER BY score DESC" % self.season)
                    query.addBindValue(league)
                    query.exec_()
                    if query.size() >= 4:
                        query.first()
                        for i in range(1, 4):
                            score = float(query.value(0))
                            idUser = int(query.value(1))

                            if idUser != self.player.id or score <= 0:
                                query.next()
                                continue

                            avatar = {
                                "url": str(Config['global']['content_url'] + "avatars/league" + str(i) + ".png")
                            }
                            if i == 1:
                                avatar.tooltip = "First in my League!"
                            elif i == 2:
                                avatar.tooltip = "Second in my League!"
                            elif i == 3:
                                avatar.tooltip = "Third in my League!"

                            self.player.avatar = avatar
                            self.leagueAvatar = avatar
                            break

                    jleague = {"league": self.player.league, "division": self.player.division}
                    self.player.leagueInfo = jleague

            ## AVATARS
            ## -------------------
            query.prepare(
                "SELECT url, tooltip FROM `avatars` LEFT JOIN `avatars_list` ON `idAvatar` = `avatars_list`.`id` WHERE `idUser` = ? AND `selected` = 1")
            query.addBindValue(self.uid)
            query.exec_()
            if query.size() > 0:
                query.first()
                avatar = {"url": str(query.value(0)), "tooltip": str(query.value(1))}
                self.player.avatar = avatar

            if self.player is not None:
                #remove ghost
                for p in self.parent.listUsers.players:
                    if p.getLogin() == self.player.getLogin():
                        if p.lobbyThread.socket:
                            p.lobbyThread.command_quit_team(dict(command="quit_team"))
                            p.lobbyThread.socket.abort()

                        if p in self.parent.listUsers.players:
                            self.parent.listUsers.players.remove(p)

                for p in self.parent.listUsers.logins:
                    if p == self.player.getLogin():
                        self.parent.listUsers.logins.remove(p)

                gameSocket, lobbySocket = self.parent.listUsers.addUser(self.player)

            else:
                return

            self.log.debug("Closing users")

            if gameSocket is not None:
                gameSocket.abort()

            if lobbySocket is not None:
                lobbySocket.abort()

            self.log.debug("Welcome")
            self.sendJSON(dict(command="welcome", email=str(self.email)))


            if len(self.player.modManager) > 0:
                self.sendJSON(dict(command="mod_manager", action="list", mods=self.player.modManager))

            tourneychannel = self.getPlayerTournament(self.player)
            if len(tourneychannel) > 0:
                channels = channels + tourneychannel

            reply = QByteArray()
            for user in self.parent.listUsers.players():
                reply.append(self.prepareBigJSON(self.parent.parent.jsonPlayer(user)))

            self.sendArray(reply)

            query = QSqlQuery(self.parent.db)
            query.prepare(
                "SELECT login.login FROM friends JOIN login ON idFriend=login.id WHERE idUser = ?")
            query.addBindValue(self.uid)
            query.exec_()

            if query.size() > 0:
                while query.next():
                    self.friendList.append(str(query.value(0)))

                jsonToSend = {"command": "social", "friends": self.friendList}
                self.sendJSON(jsonToSend)

            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT idMap FROM ladder_map_selection WHERE idUser = ?")
            query.addBindValue(self.uid)
            query.exec_()
            if query.size() > 0:
                while query.next():
                    self.ladderMapList.append(int(query.value(0)))

            query = QSqlQuery(self.parent.db)
            query.prepare(
                "SELECT login.login FROM foes JOIN login ON idFoe=login.id WHERE idUser = ?")
            query.addBindValue(self.uid)
            query.exec_()
            if query.size() > 0:
                while query.next():
                    self.foeList.append(str(query.value(0)))

                jsonToSend = {"command": "social", "foes": self.foeList}
                self.sendJSON(jsonToSend)

            self.sendModList()
            self.sendGameList()
            self.sendReplaySection()

            self.log.debug("sending new player")
            for user in self.parent.listUsers.players():

                if user.getLogin() != str(login):

                    lobby = user.lobbyThread
                    if lobby is not None:
                        lobby.sendJSON(self.parent.parent.jsonPlayer(self.player))

            if self.player.mod:
                channels.append("#moderators")
            # #channels.append("#techQuestions")
            # #channels.append("#IMBA_Cup_2")
            if self.player.clan is not None:
                channels.append("#%s_clan" % self.player.clan)

            # Useful for setting clan war on a specific day.
            #     if datetime.datetime.today().weekday() == 6:
            #         #if it's sunday, clan war!
            #         clanwar = ["BC", "B8", "SFo", "VoR", "AIx", "BFA", "OS"]
            #         if self.player.getClan() in clanwar:
            #             channels.append("#IntergalacticColosseum6")


            jsonToSend = {"command": "social", "autojoin": channels}
            self.sendJSON(jsonToSend)

            # for GW
            #channelsAvailable = ["#aeon", "#cybran", "#uef", "#seraphim"] + channels
            channelsAvailable = channels

            jsonToSend = {"command": "social", "channels": channelsAvailable}
            self.sendJSON(jsonToSend)

            # for matchmaker match...

            container = self.parent.games.getContainer("ladder1v1")
            if container is not None:
                for player in container.players:
                    if player == self.player:
                        continue
                    #minimum game quality to start a match.
                    trueSkill = self.player.ladder1v1Skill
                    deviation = trueSkill.getRating().getStandardDeviation()

                    gameQuality = 0.8
                    if deviation > 450:
                        gameQuality = 0.01
                    elif deviation > 350:
                        gameQuality = 0.1
                    elif deviation > 300:
                        gameQuality = 0.7
                    elif deviation > 250:
                        gameQuality = 0.75
                    else:
                        gameQuality = 0.8

                    curTrueSkill = player.ladder1v1Skill

                    if deviation > 350 and curTrueSkill.getRating().getConservativeRating() > 1600:
                        continue

                    curMatchQuality = self.getMatchQuality(trueSkill, curTrueSkill)
                    if curMatchQuality >= gameQuality:
                        self.addPotentialPlayer(player.getLogin())

            if self in self.parent.recorders:
                if self.pingTimer is not None and self.noSocket == False:
                    self.pingTimer.stop()
                    self.pingTimer.start(61000)

            self.log.debug("done")
        except Exception as ex:
            self.log.exception(ex)
            self.sendJSON(dict(command="notice", style="error",
                               text="Something went wrong during sign in"))

    @timed
    def getLastSeason(self):
        now = datetime.date.today()

        if (now.month == 3 and now.day < 21) or now.month < 3:
            previous = datetime.datetime(now.year - 1, 12, 21)

        elif (now.month == 6 and now.day < 21) or now.month < 6:

            previous = datetime.datetime(now.year, 0o3, 21)

        elif (now.month == 9 and now.day < 21) or now.month < 9:

            previous = datetime.datetime(now.year, 0o6, 21)

        else:

            previous = datetime.datetime(now.year, 9, 21)

        return previous

    @timed
    def command_ask_session(self, message):
        #self.log.debug("asking session")
        jsonToSend = {"command": "welcome", "session": self.session}

        if self.initTimer:
            self.initTimer.stop()
            self.initTimer = None

        if self in self.parent.recorders:
            self.pingTimer = QTimer(self)
            self.pingTimer.timeout.connect(self.ping)
            self.pingTimer.start(31000)

        self.sendJSON(jsonToSend)
        #self.log.debug("asking session done")

    @timed
    def sendModFiles(self, mod):
        modTable = "updates_" + mod
        modTableFiles = modTable + "_files"

        modFiles = []
        versionFiles = []

        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT * FROM " + modTable)

        query.exec_()

        if query.size() > 0:

            while query.next():
                fileInfo = {"uid": query.value(0), "filename": query.value(1), "path": query.value(2)}
                modFiles.append(fileInfo)

        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT * FROM " + modTableFiles)

        query.exec_()

        if query.size() > 0:

            while query.next():
                fileInfo = {"uid": query.value(0), "fileuid": query.value(1), "version": query.value(2),
                            "name": query.value(3)}
                versionFiles.append(fileInfo)

        self.sendJSON(dict(command="mod_manager_info", mod=mod, mod_files=modFiles, version_files=versionFiles))


    @timed
    def command_mod_manager_info(self, message):
        action = message['action']

        if action == "added_file":
            fileUploaded = message["file"]
            version = message["version"]
            fileuid = message["type"]
            mod = message["mod"]

            modTable = "updates_" + mod
            modTableFiles = modTable + "_files"

            query = QSqlQuery(self.parent.db)
            query.prepare("INSERT INTO " + modTableFiles + "(fileid, version, name) VALUES (?, ?, ?)")
            query.addBindValue(fileuid)
            query.addBindValue(version)
            query.addBindValue(fileUploaded)

            if not query.exec_():
                logger.error("Failed to execute DB : " + query.lastQuery())
                self.sendJSON(dict(command="notice", style="error", text="Error updating the database."))
            else:
                self.sendJSON(dict(command="notice", style="info", text="Database updated correctly."))

                self.sendModFiles(mod)

        if action == "list":
            mod = message["mod"]
            self.sendModFiles(mod)

    @timed
    def command_avatar(self, message):
        action = message['action']

        if action == "upload_avatar" and self.player.admin:
            name = message["name"]
            avatarDatas = (zlib.decompress(base64.b64decode(message["file"])))
            description = message["description"]

            writeFile = QFile(Config['global']['content_path'] + "avatars/%s" % name)

            if writeFile.open(QIODevice.WriteOnly):
                writeFile.write(avatarDatas)
            writeFile.close()

            query = QSqlQuery(self.parent.db)
            query.prepare(
                "INSERT INTO avatars_list (`url`,`tooltip`) VALUES (?,?) ON DUPLICATE KEY UPDATE `tooltip` = ?;")
            query.addBindValue(Config['global']['content_url'] + "faf/avatars/" + name)
            query.addBindValue(description)
            query.addBindValue(description)

            self.sendJSON(dict(command="notice", style="info", text="Avatar uploaded."))

            if not query.exec_():
                logger.error("Failed to execute DB : " + query.lastQuery())
                self.sendJSON(dict(command="notice", style="error", text="Avatar not correctly uploaded."))

        elif action == "list_avatar":
            avatarList = []
            if self.leagueAvatar:
                avatarList.append(self.leagueAvatar)

            query = QSqlQuery(self.parent.db)
            query.prepare(
                "SELECT url, tooltip FROM `avatars` LEFT JOIN `avatars_list` ON `idAvatar` = `avatars_list`.`id` WHERE `idUser` = ?")
            query.addBindValue(self.uid)
            query.exec_()
            if query.size() > 0:

                while query.next():
                    avatar = {"url": str(query.value(0)), "tooltip": str(query.value(1))}
                    avatarList.append(avatar)

            if len(avatarList) > 0:
                jsonToSend = {"command": "avatar", "avatarlist": avatarList}
                self.sendJSON(jsonToSend)

        elif action == "select":
            avatar = message['avatar']

            query = QSqlQuery(self.parent.db)

            query.prepare(
                "UPDATE `avatars` SET `selected` = 0 WHERE `idUser` = ?")
            query.addBindValue(self.uid)
            query.exec_()
            if avatar is not None:
                query = QSqlQuery(self.parent.db)
                query.prepare(
                    "UPDATE `avatars` SET `selected` = 1 WHERE `idAvatar` = (SELECT id FROM avatars_list WHERE avatars_list.url = ?) and `idUser` = ?")
                query.addBindValue(avatar)
                query.addBindValue(self.uid)
                query.exec_()


    @timed
    def command_game_join(self, message):
        """
        We are going to join a game.
        """

        uuid = message['uid']
        gameport = message['gameport']

        password = None
        if "password" in message:
            password = message['password']

        self.joinGame(uuid, gameport, password)

    def check_cheaters(self):
        """ When someone is cancelling a ladder game on purpose..."""
        game = self.player.getGame()
        if game:
            realGame = self.parent.games.find_by_id(self.player.getGame())
            if realGame:
                if realGame.initMode == 1 and realGame.lobbyState != "playing":
                    # player has a laddergame that isn't playing, so we suspect he is a canceller....
                    self.log.debug("Having a ladder and cancelling it...")

                    query = QSqlQuery(self.parent.db)
                    query.prepare("UPDATE `login` SET `ladderCancelled`= `ladderCancelled`+1  WHERE id = ?")
                    query.addBindValue(self.uid)
                    query.exec_()

            else:
                self.log.debug("No real game found...")

            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT `ladderCancelled` FROM `login` WHERE id = ?")
            query.addBindValue(self.uid)
            query.exec_()
            if query.size() != 0:
                attempts = query.value(0)
                if attempts:
                    if attempts >= 10:
                        return False
                else:
                    self.log.debug("Not getting the value properly a ladder and cancelling it...")

        return True

    @timed
    def command_game_matchmaking(self, message):

        mod = message.get('mod', 'matchmaker')
        state = message['state']

        if mod == "ladder1v1" and state == "start":

            if not self.check_cheaters():
                self.sendJSON(dict(command="notice", style="error",
                                   text="You are banned from the matchmaker (cancelling too many times). Please contact an admin."))
                return

        query = QSqlQuery(self.parent.db)
        query.prepare(
            "SELECT * FROM matchmaker_ban WHERE `userid` = (SELECT `id` FROM `login` WHERE `login`.`login` = ?)")
        query.addBindValue(self.player.getLogin())
        query.exec_()
        if query.size() != 0:
            self.sendJSON(dict(command="notice", style="error",
                               text="You are banned from the matchmaker. Contact an admin to have the reason."))
            return

        self.checkOldGamesFromPlayer()

        container = self.parent.games.getContainer(mod)

        if container is not None:

            if mod == "ladder1v1":
                if state == "stop":
                    for player in self.parent.listUsers.players:
                        player.lobbyThread.removePotentialPlayer(self.player.getLogin())

                elif state == "start":
                    gameport = message['gameport']
                    faction = message['faction']

                    container.removeOldGames()
                    self.player.setGamePort(gameport)
                    container.addPlayer(self.season, self.player)
                    container.searchForMatchup(self.player)
                    if faction.startswith("/"):
                        faction = faction.strip("/")

                    self.player.faction = faction

                    self.warnPotentialOpponent()


                elif state == "expand":
                    rate = message['rate']
                    self.player.expandLadder = rate
                    container.searchForMatchup(self.player)

            if mod == "matchmaker":
                if state == "faction":
                    self.player.faction = message["factionchosen"]

                elif state == "port":
                    port = message["port"]
                    self.player.setGamePort(port)

                elif state == "askingtostart":
                    players = message["players"]
                    port = message["port"]
                    self.player.setGamePort(port)
                    if self.parent.teams.isInSquad(self.player.getLogin()):
                        if not self.parent.teams.isLeader(self.player.getLogin()):
                            self.sendJSON(
                                dict(command="notice", style="error", text="Only the team leader can start searching."))
                            return
                        members = self.parent.teams.getAllMembers(self.player.getLogin())
                        if len(members) > players:
                            self.sendJSON(dict(command="notice", style="error",
                                               text="Too many players in your team for a %ivs%i game." % (
                                                   players, players)))
                            return
                        onlinePlayers = []
                        anyoneOffline = False
                        for member in members:
                            player = self.parent.listUsers.findByName(member)
                            if player:
                                player.lobbyThread.sendJSON(
                                    dict(command="matchmaker_info", action="startSearching", players=players))
                                onlinePlayers.append(player)

                            else:
                                self.parent.teams.removeFromSquad(self.player.getLogin(), member)
                                anyoneOffline = True

                        if anyoneOffline:
                            for player in onlinePlayers:
                                player.lobbyThread.sendJSON(
                                    dict(command="team_info", leader=self.player.getLogin(), members=onlinePlayers))

                        container.addPlayers(players, onlinePlayers)

                    else:
                        self.sendJSON(dict(command="matchmaker_info", action="startSearching", players=players))
                        container.addPlayers(players, [self.player])

                if state == "askingtostop":
                    if self.parent.teams.isInSquad(self.player.getLogin()):
                        if not self.parent.teams.isLeader(self.player.getLogin()):
                            self.sendJSON(
                                dict(command="notice", style="error", text="Only the team leader can stop searching."))
                            return
                        members = self.parent.teams.getAllMembers(self.player.getLogin())
                        for member in members:
                            player = self.parent.listUsers.findByName(member)
                            if player:
                                player.lobbyThread.sendJSON(
                                    dict(command="matchmaker_info", action="stopSearching"))


                    else:
                        self.sendJSON(dict(command="matchmaker_info", action="stopSearching"))


    def addPotentialPlayer(self, player):
        if player in self.ladderPotentialPlayers:
            return
        else:
            self.ladderPotentialPlayers.append(player)
            if not self.warned:
                self.warned = True
                self.sendJSON(dict(command="matchmaker_info", potential=True))

    def removePotentialPlayer(self, player):
        if player in self.ladderPotentialPlayers:
            self.ladderPotentialPlayers.remove(player)

        if len(self.ladderPotentialPlayers) == 0 and self.warned:
            self.sendJSON(dict(command="matchmaker_info", potential=False))
            self.warned = False

    def warnPotentialOpponent(self):
        for player in self.parent.listUsers.players:
            if player == self.player:
                continue
                #minimum game quality to start a match.
            trueSkill = player.ladder1v1Skill
            deviation = trueSkill.getRating().getStandardDeviation()

            gameQuality = 0.8
            if deviation > 450:
                gameQuality = 0.01
            elif deviation > 350:
                gameQuality = 0.1
            elif deviation > 300:
                gameQuality = 0.7
            elif deviation > 250:
                gameQuality = 0.75
            else:
                gameQuality = 0.8

            curTrueSkill = self.player.ladder1v1Skill

            if deviation > 350 and curTrueSkill.getRating().getConservativeRating() > 1600:
                continue

            curMatchQuality = self.getMatchQuality(trueSkill, curTrueSkill)
            if curMatchQuality >= gameQuality:
                if hasattr(player.lobbyThread, "addPotentialPlayer"):
                    player.lobbyThread.addPotentialPlayer(self.player.getLogin())

    @staticmethod
    def getMatchQuality(player1, player2):
        matchup = [player1, player2]
        gameInfo = GameInfo()
        calculator = FactorGraphTrueSkillCalculator()
        return calculator.calculateMatchQuality(gameInfo, matchup)


    def command_coop_list(self, message):
        """ requestion coop lists"""
        self.sendCoopList()

    @timed()
    def command_game_host(self, message):
        title = cgi.escape(message.get('title', ''))
        gameport = message.get('gameport')
        access = message.get('access')
        mod = message.get('mod')
        version = message.get('version')
        try:
            title.encode('ascii')
        except UnicodeEncodeError:
            self.sendJSON(dict(command="notice", style="error", text="Non-ascii characters in game name detected."))
            return

        mapname = message.get('mapname')
        password = message.get('password')
        lobby_rating = message.get('lobby_rating', 1)  # 0 = no rating inside the lobby. Default is 1.
        options = message.get('options', [])

        self.hostGame(access, title, gameport, version, mod, mapname, password, lobby_rating, options)


    def command_modvault(self, message):
        type = message["type"]
        if type == "start":
            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT * FROM table_mod ORDER BY likes DESC LIMIT 0, 100")
            query.exec_()
            if query.size() != 0:
                while query.next():
                    uid = str(query.value(1))
                    name = str(query.value(2))
                    version = int(query.value(3))
                    author = str(query.value(4))
                    isuimod = int(query.value(5))
                    isbigmod = int(query.value(6))
                    issmallmod = int(query.value(7))
                    date = query.value(8).toTime_t()
                    downloads = int(query.value(9))
                    likes = int(query.value(10))
                    played = int(query.value(11))
                    description = str(query.value(12))
                    comments = []
                    bugreports = []
                    link = Config['global']['content_url'] + "vault/" + str(query.value(13))
                    icon = str(query.value(14))
                    thumbstr = ""
                    if icon != "":
                        thumbstr = Config['global']['content_url'] + "vault/mods_thumbs/" + urllib.parse.quote(icon)

                    out = dict(command="modvault_info", thumbnail=thumbstr, link=link, bugreports=bugreports,
                               comments=comments, description=description, played=played, likes=likes,
                               downloads=downloads, date=date, uid=uid, name=name, version=version, author=author,
                               ui=isuimod, big=isbigmod, small=issmallmod)
                    self.sendJSON(out)

        elif type == "like":
            likers = []
            out = ""
            canLike = True
            uid = message["uid"]
            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT * FROM `table_mod` WHERE uid = ?")
            query.addBindValue(uid)
            if not query.exec_():
                self.log.debug(query.lastError())
            if query.size() != 0:
                query.first()
                uid = str(query.value(1))
                name = str(query.value(2))
                version = int(query.value(3))
                author = str(query.value(4))
                isuimod = int(query.value(5))
                isbigmod = int(query.value(6))
                issmallmod = int(query.value(7))
                date = query.value(8).toTime_t()
                downloads = int(query.value(9))
                likes = int(query.value(10))
                played = int(query.value(11))
                description = str(query.value(12))
                comments = []
                bugreports = []
                link = Config['global']['content_url'] + "vault/" + str(query.value(13))
                icon = str(query.value(14))
                thumbstr = ""
                if icon != "":
                    thumbstr = Config['global']['content_url'] + "vault/mods_thumbs/" + urllib.parse.quote(icon)

                out = dict(command="modvault_info", thumbnail=thumbstr, link=link, bugreports=bugreports,
                           comments=comments, description=description, played=played, likes=likes + 1,
                           downloads=downloads, date=date, uid=uid, name=name, version=version, author=author,
                           ui=isuimod, big=isbigmod, small=issmallmod)

                likerList = str(query.value(15))
                try:
                    likers = json.loads(likerList)
                    if self.uid in likers:
                        canLike = False
                    else:
                        likers.append(self.uid)
                except:
                    likers = []
            if canLike:
                query = QSqlQuery(self.parent.db)
                query.prepare("UPDATE `table_mod` SET likes=likes+1, likers=? WHERE uid = ?")
                query.addBindValue(json.dumps(likers))
                query.addBindValue(uid)
                query.exec_()
                self.sendJSON(out)



        elif type == "download":
            uid = message["uid"]
            query = QSqlQuery(self.parent.db)
            query.prepare("UPDATE `table_mod` SET downloads=downloads+1 WHERE uid = ?")
            query.addBindValue(uid)
            query.exec_()

        elif type == "addcomment":
            pass

    def prepareBigJSON(self, data_dictionary):
        """
        Simply dumps a dictionary into a string and feeds it into the QTCPSocket
        """
        try:
            data_string = json.dumps(data_dictionary)
        except:
            return
        return self.preparePacket(data_string)

    @timed()
    def sendJSON(self, data_dictionary):
        """
        Simply dumps a dictionary into a string and feeds it into the QTCPSocket
        """
        if "command" in data_dictionary:
            if data_dictionary["command"] == "game_launch":
                # if we join a game, we are not a potential player anymore
                for player in self.parent.listUsers.players:
                    player.lobbyThread.removePotentialPlayer(self.player.getLogin())

        if not self.noSocket:
            try:
                data_string = json.dumps(data_dictionary)

                if not self.noSocket:
                    self.sendReply(data_string)
            except:
                return

    @timed()
    def receiveJSON(self, data_string, stream):
        """
        A fairly pythonic way to process received strings as JSON messages.
        """
        try:
            message = json.loads(data_string)
            cmd = message['command']
            if not isinstance(cmd, str):
                raise ValueError("Command is not a string")
            getattr(self, 'command_{}'.format(cmd))(message)
        except (KeyError, ValueError) as ex:
            self.log.warning("Garbage input from client: {}".format(data_string))
            self.log.exception(ex)

    def done(self):
        if self.uid:
            query = QSqlQuery(self.parent.db)
            query.prepare("UPDATE login SET session = NULL WHERE id = ?")
            query.addBindValue(self.uid)
            query.exec_()

        self.noSocket = True
        if self.player:
            self.command_quit_team(dict(command="quit_team"))

            for player in self.parent.listUsers.players:
                player.lobbyThread.removePotentialPlayer(self.player.getLogin())
            self.checkOldGamesFromPlayer()
            self.parent.listUsers.removeUser(self.player)

        if self in self.parent.recorders:
            if self.pingTimer:
                self.pingTimer.stop()

            if self.socket:
                self.socket.readyRead.disconnect(self.readData)
                self.socket.disconnected.disconnect(self.disconnection)
                self.socket.error.disconnect(self.displayError)
                self.socket.abort()
                self.socket.deleteLater()

            self.parent.removeRecorder(self)

    def stateChange(self, socketState):
        pass

    def displayError(self, socketError):
        if socketError == QtNetwork.QAbstractSocket.RemoteHostClosedError:
            self.log.warning(self.logPrefix + "RemoteHostClosedError")

        elif socketError == QtNetwork.QAbstractSocket.HostNotFoundError:
            self.log.warning(self.logPrefix + "HostNotFoundError")
        elif socketError == QtNetwork.QAbstractSocket.ConnectionRefusedError:
            self.log.warning(self.logPrefix + "ConnectionRefusedError")
        else:
            self.log.warning(self.logPrefix + "The following Error occurred: %s." % self.socket.errorString())

