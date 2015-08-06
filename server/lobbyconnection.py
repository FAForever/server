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
import asyncio
import hashlib
import zlib
import cgi
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
import smtplib
from email.mime.text import MIMEText
import email.utils

from PySide.QtCore import QByteArray, QDataStream, QIODevice, QFile, QObject
from PySide.QtSql import QSqlQuery
import pygeoip
import trueskill
from trueskill import Rating

from server.decorators import timed, with_logger
from server.games.game import GameState
from server.players import *
from .game_service import GameService
from passwords import PW_SALT, STEAM_APIKEY, PRIVATE_KEY, decodeUniqueId, MAIL_ADDRESS
import config
from config import Config
from server.protocol import QDataStreamProtocol


gi = pygeoip.GeoIP('GeoIP.dat', pygeoip.MEMORY_CACHE)

LADDER_SEASON = "ladder_season_5"

from steam import api

api.key.set(STEAM_APIKEY)

@with_logger
class LobbyConnection(QObject):
    @timed()
    def __init__(self, context=None, games: GameService=None, players=None, db=None, db_pool=None, loop=asyncio.get_event_loop()):
        super(LobbyConnection, self).__init__()
        self.loop = loop
        self.db = db
        self.db_pool = db_pool
        self.games = games
        self.players = players
        self.context = context
        self.season = LADDER_SEASON
        self.ladderPotentialPlayers = []
        self.warned = False
        self._authenticated = False
        self.privkey = PRIVATE_KEY
        self.noSocket = False
        self.readingSocket = False
        self.player = None
        self.initPing = True
        self.ponged = False
        self.steamChecked = False
        self.logPrefix = "\t"
        self.missedPing = 0
        self.friendList = []
        self.foeList = []
        self.ladderMapList = []
        self.leagueAvatar = None
        self.email = None
        self.ip = None
        self.port = None
        self.session = int(random.randrange(0, 4294967295))
        self.protocol = None
        self._logger.debug("LobbyConnection initialized")

    @property
    def authenticated(self):
        return self._authenticated

    @asyncio.coroutine
    def on_connection_made(self, protocol: QDataStreamProtocol, peername: (str, int)):
        self.protocol = protocol
        self.ip, self.port = peername

    def abort(self):
        self._authenticated = False
        self.protocol.writer.write_eof()
        self.protocol.reader.feed_eof()

    @asyncio.coroutine
    def on_message_received(self, message):
        """
        Dispatches incoming messages
        """
        try:
            cmd = message['command']
            if not isinstance(cmd, str):
                raise ValueError("Command is not a string")
            if not self._authenticated:
                if cmd not in ['hello', 'ask_session', 'create_account', 'ping', 'pong']:
                    self.abort()
            handler = getattr(self, 'command_{}'.format(cmd))
            if asyncio.iscoroutinefunction(handler):
                yield from handler(message)
            else:
                handler(message)
        except (KeyError, ValueError) as ex:
            self._logger.warning("Garbage command: {}".format(message))
            self._logger.exception(ex)
        except Exception as ex:
            self.protocol.send_message({'command': 'invalid'})
            self._logger.warning("Error processing command")
            self._logger.exception(ex)

    def command_ping(self, msg):
        self.sendReply('PONG')

    def command_pong(self, msg):
        self.ponged = True

    def command_upload_mod(self, msg):
        zipmap = msg['name']
        infos = msg['info']
        fileDatas = msg['data']
        message = infos

        for key, readable in {
            'name': "mod name",
            'uid': "uid",
            'description': "description",
            'author': 'author',
            'ui_only': 'mod type',
            'version': 'version',
            'big': 'big',
            'small': 'small'
        }.items():
            if key not in message:
                self.sendJSON(dict(command="notice", style="error", text="No {} provided.".format(readable)))
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

        query = QSqlQuery(self.db)
        query.prepare("SELECT * FROM table_mod WHERE uid = ?")
        query.addBindValue(uid)
        query.exec_()
        if query.size() != 0:
            error = name + " uid " + uid + "already exists in the database."
            self.sendJSON(dict(command="notice", style="error", text=error))
            return

        query.prepare("SELECT filename FROM table_mod WHERE filename LIKE '%" + zipmap + "%'")
        query.exec_()
        if query.size() != 0:
            self.sendJSON(dict(command="notice", style="error",
                               text="This file (%s) is already in the database !" % str(zipmap)))
            return
        writeFile = QFile(Config['content_path'] + "vault/mods/%s" % zipmap)

        if writeFile.open(QIODevice.WriteOnly):
            writeFile.write(fileDatas)
        writeFile.close()

        if not zipfile.is_zipfile(Config['content_path'] + "vault/mods/%s" % zipmap):
            self.sendJSON(
                dict(command="notice", style="error", text="Cannot unzip mod. Upload error ?"))
            return
        zip = zipfile.ZipFile(Config['content_path'] + "vault/mods/%s" % zipmap, "r",
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
                        os.path.join(Config['content_path'] + "vault/mods_thumbs/",
                                     zipmap.replace(".zip", ".png")), "wb")
                    icon = zipmap.replace(".zip", ".png")

                    shutil.copyfileobj(source, target)
                    source.close()
                    target.close()

            #add the datas in the db
            filename = "mods/%s" % zipmap

            query = QSqlQuery(self.db)
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
                self._logger.debug(query.lastError())
        zip.close()

        self.sendJSON(dict(command="notice", style="info", text="Mod correctly uploaded."))

    def command_upload_map(self, msg):
        zipmap = msg['name']
        infos = msg['info']
        fileDatas = msg['data']

        message = infos

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

        query = QSqlQuery(self.db)
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
            writeFile = QFile(Config['content_path'] + "vault/maps/%s" % zipmap)

            if writeFile.open(QIODevice.WriteOnly):
                writeFile.write(fileDatas)
            writeFile.close()

            if zipfile.is_zipfile(Config['content_path'] + "vault/maps/%s" % zipmap):
                zip = zipfile.ZipFile(Config['content_path'] + "vault/maps/%s" % zipmap, "r",
                                      zipfile.ZIP_DEFLATED)

                if zip.testzip() is None:

                    for member in zip.namelist():
                        filename = os.path.basename(member)
                        if not filename:
                            continue
                        if filename.endswith(".small.png"):
                            source = zip.open(member)
                            target = open(
                                os.path.join(Config['content_path'] + "vault/map_previews/small/",
                                             filename.replace(".small.png", ".png")), "wb")

                            shutil.copyfileobj(source, target)
                            source.close()
                            target.close()
                        elif filename.endswith(".large.png"):
                            source = zip.open(member)
                            target = open(
                                os.path.join(Config['content_path'] + "vault/map_previews/large/",
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
                    query = QSqlQuery(self.db)
                    query.prepare("SELECT mapuid FROM table_map WHERE name = ?")
                    query.addBindValue(name)
                    query.exec_()
                    if query.size() != 0:
                        query.first()
                        gmuid = int(query.value(0))

                    else:
                        query = QSqlQuery(self.db)
                        query.prepare("SELECT MAX(mapuid) FROM table_map")
                        query.exec_()
                        if query.size() != 0:
                            query.first()
                            gmuid = int(query.value(0)) + 1

                    #add the data in the db
                    filename = "maps/%s" % zipmap

                    query = QSqlQuery(self.db)
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
                        self._logger.debug(query.lastError())

                    uuid = query.lastInsertId()

                    query.prepare("INSERT INTO `table_map_uploaders`(`mapid`, `userid`) VALUES (?,?)")
                    query.addBindValue(uuid)
                    query.addBindValue(self.player.id)
                    if not query.exec_():
                        self._logger.debug(query.lastError())

                    if unranked:
                        query.prepare("INSERT INTO `table_map_unranked`(`id`) VALUES (?)")
                        query.addBindValue(uuid)
                        if not query.exec_():
                            self._logger.debug(query.lastError())

                zip.close()

                self.sendJSON(dict(command="notice", style="info", text="Map correctly uploaded."))
            else:
                self.sendJSON(
                    dict(command="notice", style="error", text="Cannot unzip map. Upload error ?"))
        else:
            self.sendJSON(
                dict(command="notice", style="error", text="This map is already in the database !"))

    def command_create_account(self, message):
        login = message['login']
        email = message['email']
        password = message['password']

        username_pattern = re.compile(r"^[^,]{1,20}$")
        email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}$")
        if not email_pattern.match(email):
            self.sendJSON(dict(command="notice", style="info",
                               text="Please use a valid email address."))
            self.sendReply("LOGIN_AVAILABLE", "no", login)
            return

        if not username_pattern.match(login):
            self.sendJSON(dict(command="notice", style="info",
                               text="Please don't use \",\" in your username."))
            self.sendReply("LOGIN_AVAILABLE", "no", login)
            return

        query = QSqlQuery(self.db)
        query.prepare("SELECT id FROM `login` WHERE LOWER(`login`) = ?")
        query.addBindValue(login.lower())
        if not query.exec_():
            self._logger.debug("Error inserting login %s", login)
            self._logger.debug(query.lastError())
            self.sendReply("LOGIN_AVAILABLE", "no", login)
            return

        if query.size() != 0:
            self._logger.debug("Login not available: %s", login)
            self.sendReply("LOGIN_AVAILABLE", "no", login)
            return

        query.prepare("INSERT INTO login (login, password, email) VALUES (?,?,?)")
        query.addBindValue(login)
        query.addBindValue(password)
        query.addBindValue(email)

        if not query.exec_():
            self._logger.debug("Error inserting login %s", login)
            self._logger.debug(query.lastError())
            self.sendReply("LOGIN_AVAILABLE", "no", login)
            return

        uid = query.lastInsertId()

        exp = time.strftime("%Y-%m-%d %H:%m:%S", time.gmtime())
        key = hashlib.md5()
        key.update((login + '_' + email + str(random.randrange(0, 10000)) + exp + PW_SALT).encode())
        keyHex = key.hexdigest()
        query.prepare("INSERT INTO `validate_account` (`UserID`,`Key`,`expDate`) VALUES (?,?,?)")
        query.addBindValue(uid)
        query.addBindValue(keyHex)
        query.addBindValue(exp)
        query.exec_()
        self._logger.debug("Sending registration mail")
        link = {'a': 'validate', 'email': keyHex, 'u': base64.b64encode(str(uid))}
        passwordLink = Config['app_url'] + "validateAccount.php?" + urllib.parse.urlencode(link)

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
        msg['To'] = email.utils.formataddr((login, email))

        self._logger.debug("sending mail to " + email)
        #self.log.debug(msg.as_string())
        #s = smtplib.SMTP(config['global']['smtp_server'])
        s = smtplib.SMTP_SSL(Config['smtp_server'], 465, Config['smtp_server'],
                             timeout=5)
        s.login(Config['smtp_username'], Config['smtp_password'])

        s.sendmail(MAIL_ADDRESS, [email], msg.as_string())
        s.quit()

        self.sendJSON(dict(command="notice", style="info",
                           text="A e-mail has been sent with the instructions to validate your account"))
        self._logger.debug("sent mail")
        self.sendReply("LOGIN_AVAILABLE", "yes", login)

    @timed()
    def send_tutorial_section(self):
        reply = []

        query = QSqlQuery(self.db)
        query.prepare("SELECT `section`,`description` FROM `tutorial_sections`")
        query.exec_()
        if query.size() > 0:
            while query.next():
                jsonToSend = {"command": "tutorials_info", "section": query.value(0), "description": query.value(1)}
                reply.append(jsonToSend)

        query.prepare(
            "SELECT tutorial_sections.`section`,`name`,`url`, `tutorials`.`description`, `map` FROM `tutorials` LEFT JOIN  tutorial_sections ON tutorial_sections.id = tutorials.section ORDER BY `tutorials`.`section`, name")
        query.exec_()
        if query.size() > 0:
            while query.next():
                jsonToSend = {"command": "tutorials_info", "tutorial": query.value(1), "url": query.value(2),
                              "tutorial_section": query.value(0), "description": query.value(3),
                              "mapname": query.value(4)}
                reply.append(jsonToSend)

        self.protocol.send_messages(reply)

    @timed()
    def send_coop_maps(self):
        query = QSqlQuery(self.db)
        query.prepare("SELECT name, description, filename, type, id FROM `coop_map`")
        query.exec_()
        maps = []
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
                maps.append(jsonToSend)

        self.protocol.send_messages(maps)

    @timed()
    def send_mod_list(self):
        self.protocol.send_messages(self.games.all_game_modes())

    @timed()
    def send_game_list(self):
        self.protocol.send_messages([game.to_dict() for game in self.games.active_games])

    @timed()
    def sendReply(self, action, *args, **kwargs):
        if self in self.context:
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

            asyncio.async(self.protocol.send_raw(reply))

    def command_fa_state(self, message):
        state = message["state"]
        if state == "on":
            if self.player.getAction() == "NOTHING":
                self.player.setAction("FA_LAUNCHED")
        else:
            self.player.setAction("NOTHING")

    def command_ladder_maps(self, message):
        maplist = message['maps']
        toAdd = set(maplist) - set(self.ladderMapList)
        if len(toAdd) > 0:
            for uid in toAdd:
                query = QSqlQuery(self.db)
                query.prepare("INSERT INTO ladder_map_selection (idUser, idMap) values (?,?)")
                query.addBindValue(self.player.id)
                query.addBindValue(uid)
                if not query.exec_():
                    self._logger.debug(query.lastError())

        toRemove = set(self.ladderMapList) - set(maplist)
        if len(toRemove) > 0:
            for uid in toRemove:
                query = QSqlQuery(self.db)
                query.prepare("DELETE FROM ladder_map_selection WHERE idUser = ? and idMap = ?")
                query.addBindValue(self.player.id)
                query.addBindValue(uid)
                if not query.exec_():
                    self._logger.debug(query.lastError())

        self.ladderMapList = maplist

    @timed()
    def command_social(self, message):
        success = False
        if "friends" in message:
            friendlist = message['friends']
            toAdd = set(friendlist) - set(self.friendList)

            if len(toAdd) > 0:

                for friend in toAdd:
                    query = QSqlQuery(self.db)
                    query.prepare(
                        "INSERT INTO friends (idUser, idFriend) values (?,(SELECT id FROM login WHERE login.login = ?))")
                    query.addBindValue(self.player.id)
                    query.addBindValue(friend)
                    query.exec_()

            toRemove = set(self.friendList) - set(friendlist)

            if len(toRemove) > 0:
                for friend in toRemove:
                    query = QSqlQuery(self.db)
                    query.prepare(
                        "DELETE FROM friends WHERE idFriend = (SELECT id FROM login WHERE login.login = ?) AND idUser = ?")
                    query.addBindValue(friend)
                    query.addBindValue(self.player.id)
                    query.exec_()

            self.friendList = friendlist
            success = True

        if "foes" in message:
            foelist = message['foes']
            toAdd = set(foelist) - set(self.foeList)

            if len(toAdd) > 0:

                for foe in toAdd:
                    query = QSqlQuery(self.db)
                    query.prepare(
                        "INSERT INTO foes (idUser, idFoe) values (?,(SELECT id FROM login WHERE login.login = ?))")
                    query.addBindValue(self.player.id)
                    query.addBindValue(foe)
                    query.exec_()

            toRemove = set(self.foeList) - set(foelist)

            if len(toRemove) > 0:
                for foe in toRemove:
                    query = QSqlQuery(self.db)
                    query.prepare(
                        "DELETE FROM foes WHERE idFoe = (SELECT id FROM login WHERE login.login = ?) AND idUser = ?")
                    query.addBindValue(foe)
                    query.addBindValue(self.player.id)
                    query.exec_()

            self.foeList = foelist
            success = True

        if not success:
            raise KeyError('no valid social action')

    @timed()
    def resendMail(self, login):
        #self.log.debug("resending mail")       
        query = QSqlQuery(self.db)

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
            passwordLink = Config['app_url'] + "validateAccount.php?" + urllib.parse.urlencode(link)
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
            s = smtplib.SMTP_SSL(Config['smtp_server'], 465, Config['smtp_server'], timeout=5)
            s.login(Config['smtp_username'], Config['smtp_password'])
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

            player = self.players.findByName(who)
            if player:
                self._logger.info('Administrative action: {} closed game for {}'.format(self.player, player))
                player.lobbyThread.sendJSON(dict(command="notice", style="info",
                                   text=("Your game was closed by an administrator ({admin_name}). "
                                         "Please refer to our rules for the lobby/game here {rule_link}."
                                   .format(admin_name=self.player.login,
                                           rule_link=config.RULE_LINK))))
                player.lobbyThread.sendJSON(dict(command="notice", style="kill"))

        elif action == "join_channel" and self.player.mod:
            whos = message['users']
            channel = message['channel']

            for who in whos:
                player = self.players.findByName(who)
                if player:
                    player.lobbyThread.sendJSON(dict(command="social", autojoin=[channel]))

        elif action == "closelobby" and self.player.admin:
            who = message['user']

            player = self.players.findByName(who)
            if player:
                self._logger.info('Administrative action: {} closed game for {}'.format(self.player, player))
                player.lobbyThread.sendJSON(dict(command="notice", style="info",
                                   text=("Your client was closed by an administrator ({admin_name}). "
                                         "Please refer to our rules for the lobby/game here {rule_link}."
                                   .format(admin_name=self.player.login,
                                           rule_link=config.RULE_LINK))))
                player.lobbyThread.sendJSON(dict(command="notice", style="kick"))
                player.lobbyThread.abort()

        elif action == "requestavatars" and self.player.admin:
            query = QSqlQuery(self.db)
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
            query = QSqlQuery(self.db)
            query.prepare("DELETE FROM `avatars` WHERE `idUser` = ? AND `idAvatar` = ?")
            query.addBindValue(iduser)
            query.addBindValue(idavatar)
            query.exec_()

        elif action == "list_avatar_users" and self.player.admin:
            avatar = message['avatar']
            if avatar is not None:
                query = QSqlQuery(self.db)
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

            query = QSqlQuery(self.db)
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

    def check_user_login(self, cursor, login, password):
        # TODO: Hash passwords server-side so the hashing actually *does* something.
        yield from cursor.execute("SELECT login.id as id, login.validated as validated,"
                                  "login.email as email, login.steamchecked as steamchecked,"
                                  "lobby_ban.reason as reason "
                                  "FROM login LEFT JOIN lobby_ban ON login.id = lobby_ban.idUser "
                                  "WHERE login=%s AND password=%s", (login, password))

        if cursor.rowcount != 1:
            self._logger.info("Invalid login or password")
            self.sendJSON(dict(command="notice", style="error",
                               text="Login not found or password incorrect. They are case sensitive."))
            return

        player_id, validated, self.email, self.steamChecked, ban_reason = yield from cursor.fetchone()
        if ban_reason != None:
            reason = "You are banned from FAF.\n Reason :\n " + ban_reason
            self.sendJSON(dict(command="notice", style="error", text=reason))
            return

        if validated == 0:
            validate_account_url = "{}faf/validateAccount.php".format(Config['app_url'])
            reason = ("Your account is not validated. Please visit <a href='{}'>{}</a>. "
                      "<br>Please re-create an account if your email is not correct (<b>{}</b>)"
                      .format(validate_account_url, validate_account_url, self.email))
            self.resendMail(login)
            self.sendJSON(dict(command="notice", style="error", text=reason))
            return

        self._logger.debug("Login from: {}, {}, {}".format(player_id, self.email, self.session))
        self._authenticated = True

        return player_id

    @asyncio.coroutine
    def command_hello(self, message):
        try:
            version = message['version']
            login = message['login'].strip()
            password = message['password']
            uniqueId = decodeUniqueId(self, message['unique_id'], login)

            self.logPrefix = login + "\t"

            # Check their client is reporting the right version number.
            # TODO: Do this somewhere less insane. (no need to query our db for this every login!)
            with (yield from self.db_pool) as conn:
                cursor = yield from conn.cursor()
                yield from cursor.execute("SELECT version, file FROM version_lobby ORDER BY id DESC LIMIT 1")
                versionDB, updateFile = yield from cursor.fetchone()

                # Version of zero represents a developer build.
                if version < versionDB and version != 0:
                    self.sendJSON(dict(command="welcome", update=updateFile))
                    return

                player_id = self.check_user_login(cursor, login, password)

                # Login was not approved.
                if player_id == None:
                    return

                yield from cursor.execute("UPDATE login "
                                          "SET `session`=%s, ip=%s "
                                          "WHERE id=%s", (self.session, self.ip, player_id))

            if not self.steamChecked:
                if uniqueId is None:
                    self.sendJSON(dict(command="notice", style="error",
                                       text="Unique Id found for another user.<br>Multiple accounts are not allowed.<br><br>Try SteamLink: <a href='" +
                                            Config['app_url'] + "faf/steam.php'>" + Config[
                                                'app_url'] + "faf/steam.php</a>"))
                    return
                    # the user is not steam Checked.
                query = QSqlQuery(self.db)
                query.prepare("SELECT uniqueid FROM steam_uniqueid WHERE uniqueId = ?")
                query.addBindValue(uniqueId)
                query.exec_()
                if query.size() > 0:
                    self.sendJSON(dict(command="notice", style="error",
                                       text="This computer has been used by a steam account.<br>You have to authentify your account on steam too in order to use it on this computer :<br>SteamLink: <a href='" +
                                            Config['app_url'] + "faf/steam.php'>" + Config[
                                                'app_url'] + "faf/steam.php</a>"))
                    return

                # check for another account using the same uniqueId as us.
                query = QSqlQuery(self.db)
                query.prepare("SELECT id, login FROM login WHERE uniqueId = ? AND id != ?")
                query.addBindValue(uniqueId)
                query.addBindValue(player_id)
                query.exec_()

                if query.size() == 1:
                    query.first()

                    idFound = int(query.value(0))
                    otherName = str(query.value(1))

                    self._logger.debug("%i (%s) is a smurf of %s" % (self.player.id, login, otherName))
                    self.sendJSON(dict(command="notice", style="error",
                                       text="This computer is tied to this account : %s.<br>Multiple accounts are not allowed.<br>You can free this computer by logging in with that account (%s) on another computer.<br><br>Or Try SteamLink: <a href='" +
                                            Config['app_url'] + "faf/steam.php'>" +
                                            Config['app_url'] + "faf/steam.php</a>" % (
                                           otherName, otherName)))

                    query2 = QSqlQuery(self.db)
                    query2.prepare("INSERT INTO `smurf_table`(`origId`, `smurfId`) VALUES (?,?)")
                    query2.addBindValue(player_id)
                    query2.addBindValue(idFound)
                    query2.exec_()
                    return

                query = QSqlQuery(self.db)
                query.prepare("UPDATE login SET ip = ?, uniqueId = ? WHERE id = ?")
                query.addBindValue(self.ip)
                query.addBindValue(str(uniqueId))
                query.addBindValue(player_id)
                query.exec_()
            else:
                query = QSqlQuery(self.db)
                query.prepare("INSERT INTO `steam_uniqueid`(`uniqueid`) VALUES (?)")
                query.addBindValue(str(uniqueId))
                query.exec_()

            query = QSqlQuery(self.db)
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
                self._logger.error(query.lastError())

            self.player = Player(login=str(login),
                                 session=self.session,
                                 ip=self.ip,
                                 port=self.port,
                                 uuid=player_id,
                                 lobbyThread=self)
            self.player.lobbyVersion = version
            self.player.resolvedAddress = self.player.ip
            yield from self.players.fetch_player_data(self.player)

            self.player.faction = random.randint(1, 4)

            ## ADMIN
            ## --------------------
            self.player.admin = False
            self.player.mod = False
            query.prepare("SELECT `group` FROM `lobby_admin` WHERE `user_id` = ?")
            query.addBindValue(self.player.id)
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

            country = gi.country_code_by_addr(self.ip)
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
                                "url": str(Config['content_url'] + "avatars/div" + str(i) + ".png")
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
                                "url": str(Config['content_url'] + "avatars/league" + str(i) + ".png")
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
            query.addBindValue(self.player.id)
            query.exec_()
            if query.size() > 0:
                query.first()
                avatar = {"url": str(query.value(0)), "tooltip": str(query.value(1))}
                self.player.avatar = avatar

            for p in self.players.players:
                if p.login == self.player.login:
                    if hasattr(p, 'lobbyThread'):
                        p.lobbyThread.abort()

                    if p in self.players.players:
                        self.players.players.remove(p)

            for p in self.players.logins:
                if p == self.player.getLogin():
                    self.players.logins.remove(p)

            gameSocket, lobbySocket = self.players.addUser(self.player)

            if gameSocket is not None:
                gameSocket.abort()

            if lobbySocket is not None:
                lobbySocket.abort()

            self._logger.debug("Welcome")
            self.sendJSON(dict(command="welcome", email=str(self.email), id=self.player.id))

            self.protocol.send_messages(
                [player.to_dict()
                 for player in self.players.players]
            )

            query = QSqlQuery(self.db)
            query.prepare(
                "SELECT login.login FROM friends JOIN login ON idFriend=login.id WHERE idUser = ?")
            query.addBindValue(self.player.id)
            query.exec_()

            if query.size() > 0:
                while query.next():
                    self.friendList.append(str(query.value(0)))

                jsonToSend = {"command": "social", "friends": self.friendList}
                self.sendJSON(jsonToSend)

            query = QSqlQuery(self.db)
            query.prepare("SELECT idMap FROM ladder_map_selection WHERE idUser = ?")
            query.addBindValue(self.player.id)
            query.exec_()
            if query.size() > 0:
                while query.next():
                    self.ladderMapList.append(int(query.value(0)))

            query = QSqlQuery(self.db)
            query.prepare(
                "SELECT login.login FROM foes JOIN login ON idFoe=login.id WHERE idUser = ?")
            query.addBindValue(self.player.id)
            query.exec_()
            if query.size() > 0:
                while query.next():
                    self.foeList.append(str(query.value(0)))

                jsonToSend = {"command": "social", "foes": self.foeList}
                self.sendJSON(jsonToSend)

            self.send_mod_list()
            self.send_game_list()
            self.send_tutorial_section()

            player_info = self.player.to_dict()
            for player in self.players.players:
                if player != self.player:
                    lobby = player.lobby_connection
                    if lobby is not None:
                        lobby.sendJSON(player_info)

            channels = []
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

            container = self.games.getContainer("ladder1v1")
            if container is not None:
                for player in container.players:
                    if player == self.player:
                        continue
                    #minimum game quality to start a match.
                    (mean, deviation) = self.player.ladder_rating

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

                    (match_mean, match_deviation) = player.ladder_rating

                    if deviation > 350 and match_mean - 3 * match_deviation > 1600:
                        continue

                    quality = trueskill.quality_1vs1(Rating(*self.player.ladder_rating),
                                                     Rating(*player.ladder_rating))
                    if quality >= gameQuality:
                        self.addPotentialPlayer(player.getLogin())

        except Exception as ex:
            self._logger.exception(ex)
            self.sendJSON(dict(command="notice", style="error",
                               text="Something went wrong during sign in"))
            self.abort()

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
        jsonToSend = {"command": "welcome", "session": self.session}
        self.sendJSON(jsonToSend)

    @timed
    def sendModFiles(self, mod):
        modTable = "updates_" + mod
        modTableFiles = modTable + "_files"

        modFiles = []
        versionFiles = []

        query = QSqlQuery(self.db)
        query.prepare("SELECT * FROM " + modTable)

        query.exec_()

        if query.size() > 0:

            while query.next():
                fileInfo = {"uid": query.value(0), "filename": query.value(1), "path": query.value(2)}
                modFiles.append(fileInfo)

        query = QSqlQuery(self.db)
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

            query = QSqlQuery(self.db)
            query.prepare("INSERT INTO " + modTableFiles + "(fileid, version, name) VALUES (?, ?, ?)")
            query.addBindValue(fileuid)
            query.addBindValue(version)
            query.addBindValue(fileUploaded)

            if not query.exec_():
                self._logger.error("Failed to execute DB : " + query.lastQuery())
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
            try:
                avatarDatas = (zlib.decompress(base64.b64decode(message["file"])))
            except:
                raise KeyError('invalid file')
            description = message["description"]

            writeFile = QFile(Config['content_path'] + "avatars/%s" % name)

            if writeFile.open(QIODevice.WriteOnly):
                writeFile.write(avatarDatas)
            writeFile.close()

            query = QSqlQuery(self.db)
            query.prepare(
                "INSERT INTO avatars_list (`url`,`tooltip`) VALUES (?,?) ON DUPLICATE KEY UPDATE `tooltip` = ?;")
            query.addBindValue(Config['content_url'] + "faf/avatars/" + name)
            query.addBindValue(description)
            query.addBindValue(description)

            if not query.exec_():
                self._logger.error("Failed to execute DB : " + query.lastQuery())
                self.sendJSON(dict(command="notice", style="error", text="Avatar not correctly uploaded."))
            else:
                self.sendJSON(dict(command="notice", style="info", text="Avatar uploaded."))
        elif action == "list_avatar":
            avatarList = []
            if self.leagueAvatar:
                avatarList.append(self.leagueAvatar)

            query = QSqlQuery(self.db)
            query.prepare(
                "SELECT url, tooltip FROM `avatars` LEFT JOIN `avatars_list` ON `idAvatar` = `avatars_list`.`id` WHERE `idUser` = ?")
            query.addBindValue(self.player.id)
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

            query = QSqlQuery(self.db)

            # remove old avatar
            query.prepare(
                "UPDATE `avatars` SET `selected` = 0 WHERE `idUser` = ?")
            query.addBindValue(self.player.id)
            query.exec_()
            if avatar is not None:
                query = QSqlQuery(self.db)
                query.prepare(
                    "UPDATE `avatars` SET `selected` = 1 WHERE `idAvatar` = (SELECT id FROM avatars_list WHERE avatars_list.url = ?) and `idUser` = ?")
                query.addBindValue(avatar)
                query.addBindValue(self.player.id)
                query.exec_()
        else:
            raise KeyError('invalid action')

    @timed
    def command_game_join(self, message):
        """
        We are going to join a game.
        """
        assert isinstance(self.player, Player)

        uuid = message['uid']
        port = message['gameport']
        password = message.get('password', None)

        self._logger.debug("joining: {}:{} with pw: {}".format(uuid, port, password))
        game = self.games.find_by_id(uuid)
        self._logger.debug("game found: {}".format(game))

        if not game or game.state != GameState.LOBBY:
            self._logger.debug("Game not in lobby state: {}".format(game))
            self.sendJSON(dict(command="notice", style="info", text="The game you are trying to join is not ready."))
            return

        if game.password != password:
            self.sendJSON(dict(command="notice", style="info", text="Bad password (it's case sensitive)"))
            return

        self.player.setAction("JOIN")
        self.player.wantToConnectToGame = True
        self.player.setGamePort(port)
        self.player.localGamePort = port
        self.player.game = game

        response = {"command": "game_launch",
                    "mod": game.game_mode,
                    "uid": uuid,
                    "args": ["/numgames " + str(self.player.numGames)]}

        if len(game.mods) > 0:
            response["sim_mods"] = game.mods

        self.sendJSON(response)

    def check_cheaters(self):
        """ When someone is cancelling a ladder game on purpose..."""
        game = self.player.game
        if game:
            if game.gamemod == 'ladder1v1' and game.state != GameState.LIVE:
                # player has a laddergame that isn't playing, so we suspect he is a canceller....
                self._logger.debug("Detected cancelled ladder for {} {}".format(self.player, game))

                query = QSqlQuery(self.db)
                query.prepare("UPDATE `login` SET `ladderCancelled`= `ladderCancelled`+1  WHERE id = ?")
                query.addBindValue(self.player.id)
                query.exec_()

            else:
                self._logger.debug("No real game found...")

            query = QSqlQuery(self.db)
            query.prepare("SELECT `ladderCancelled` FROM `login` WHERE id = ?")
            query.addBindValue(self.player.id)
            query.exec_()
            if query.size() != 0:
                attempts = query.value(0)
                if attempts and attempts >= 10:
                    return False
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

        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT * FROM matchmaker_ban WHERE `userid` = (SELECT `id` FROM `login` WHERE `login`.`login` = ?)")
        query.addBindValue(self.player.getLogin())
        query.exec_()
        if query.size() != 0:
            self.sendJSON(dict(command="notice", style="error",
                               text="You are banned from the matchmaker. Contact an admin to have the reason."))
            return


        container = self.games.getContainer(mod)

        if container is not None:

            if mod == "ladder1v1":
                if state == "stop":
                    for player in self.players.players:
                        if player.lobbyThread:
                            player.lobbyThread.removePotentialPlayer(self.player.getLogin())

                elif state == "start":
                    gameport = message['gameport']
                    faction = message['faction']

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
        for player in self.players.players:
            if player == self.player:
                continue
                #minimum game quality to start a match.
            mean, deviation = player.ladder_rating

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

            if deviation > 350 and mean - 3*deviation > 1600:
                continue

            curMatchQuality = self.getMatchQuality(self.player, player)
            if curMatchQuality >= gameQuality:
                if hasattr(player.lobbyThread, "addPotentialPlayer"):
                    player.lobbyThread.addPotentialPlayer(self.player.getLogin())

    @staticmethod
    def getMatchQuality(player1: Player, player2: Player):
        return trueskill.quality_1vs1(player1.ladder_rating, player2.ladder_rating)


    def command_coop_list(self, message):
        """ requestion coop lists"""
        self.send_coop_maps()

    @timed()
    def command_game_host(self, message):
        assert isinstance(self.player, Player)

        title = cgi.escape(message.get('title', ''))
        port = message.get('gameport')
        access = message.get('access')
        mod = message.get('mod')
        version = message.get('version')
        try:
            title.encode('ascii')
        except UnicodeEncodeError:
            self.sendJSON(dict(command="notice", style="error", text="Non-ascii characters in game name detected."))
            return

        if self.player.in_game:
            self.sendJSON(dict(command="notice", style="error", text="You are already in a game"))
            return

        mapname = message.get('mapname')
        password = message.get('password')

        game = self.games.create_game(**{
            'visibility': access,
            'game_mode': mod.lower(),
            'host': self.player,
            'name': title if title else self.player.login,
            'mapname': mapname,
            'password': password,
            'version': None
        })

        self.player.action = "HOST"
        self.player.wantToConnectToGame = True
        self.player.game = game
        self.player.setGamePort(port)
        self.player.localGamePort = port

        self.sendJSON({"command": "game_launch",
                       "mod": mod,
                       "uid": game.uuid,
                       "version": version,
                       "args": ["/numgames " + str(self.player.numGames)]})

    def command_modvault(self, message):
        type = message["type"]
        if type == "start":
            query = QSqlQuery(self.db)
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
                    link = Config['content_url'] + "vault/" + str(query.value(13))
                    icon = str(query.value(14))
                    thumbstr = ""
                    if icon != "":
                        thumbstr = Config['content_url'] + "vault/mods_thumbs/" + urllib.parse.quote(icon)

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
            query = QSqlQuery(self.db)
            query.prepare("SELECT * FROM `table_mod` WHERE uid = ? LIMIT 1")
            query.addBindValue(uid)
            if not query.exec_():
                self._logger.debug(query.lastError())
            if query.size() == 1:
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
                link = Config['content_url'] + "vault/" + str(query.value(13))
                icon = str(query.value(14))
                thumbstr = ""
                if icon != "":
                    thumbstr = Config['content_url'] + "vault/mods_thumbs/" + urllib.parse.quote(icon)

                out = dict(command="modvault_info", thumbnail=thumbstr, link=link, bugreports=bugreports,
                           comments=comments, description=description, played=played, likes=likes + 1,
                           downloads=downloads, date=date, uid=uid, name=name, version=version, author=author,
                           ui=isuimod, big=isbigmod, small=issmallmod)

                likerList = str(query.value(15))
                try:
                    likers = json.loads(likerList)
                    if self.player.id in likers:
                        canLike = False
                    else:
                        likers.append(self.player.id)
                except:
                    likers = []
                if canLike:
                    query = QSqlQuery(self.db)
                    query.prepare("UPDATE `table_mod` SET likes=likes+1, likers=? WHERE uid = ?")
                    query.addBindValue(json.dumps(likers))
                    query.addBindValue(uid)
                    query.exec_()
                    self.sendJSON(out)



        elif type == "download":
            uid = message["uid"]
            query = QSqlQuery(self.db)
            query.prepare("UPDATE `table_mod` SET downloads=downloads+1 WHERE uid = ?")
            query.addBindValue(uid)
            query.exec_()
            # TODO: add response message

        elif type == "addcomment":
            # TODO: implement
            raise NotImplementedError('addcomment not implemented')
        else:
            raise ValueError('invalid type argument')

    @timed()
    def sendJSON(self, data_dictionary):
        """
        Simply dumps a dictionary into a string and feeds it into the QTCPSocket
        """
        if "command" in data_dictionary:
            if data_dictionary["command"] == "game_launch":
                # if we join a game, we are not a potential player anymore
                for player in self.players:
                    if player.lobbyThread:
                        player.lobbyThread.removePotentialPlayer(self.player.getLogin())

        try:
            self.protocol.send_message(data_dictionary)
        except Exception as ex:
            self._logger.exception(ex)

    def on_connection_lost(self):
        query = QSqlQuery(self.db)
        query.prepare("UPDATE login SET session = NULL WHERE id = ?")
        query.addBindValue(self.player.id)
        query.exec_()

        for player in self.players.players:
            if player.lobbyThread:
                player.lobbyThread.removePotentialPlayer(self.player.login)
        self.players.remove_player(self.player)

