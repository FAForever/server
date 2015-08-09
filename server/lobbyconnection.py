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
import rsa
import time
import smtplib
import string
from email.mime.text import MIMEText
import email.utils

from PySide.QtCore import QByteArray, QDataStream, QIODevice, QFile, QObject
from PySide.QtSql import QSqlQuery
from Crypto import Random
from Crypto.Random.random import choice
from Crypto.Cipher import Blowfish
from Crypto.Cipher import AES
import pygeoip
import trueskill
from trueskill import Rating

from server.decorators import timed, with_logger
from server.games.game import GameState
from server.players import *
from .game_service import GameService
from passwords import PRIVATE_KEY, MAIL_ADDRESS, VERIFICATION_HASH_SECRET, VERIFICATION_SECRET_KEY
import config
from config import Config
from server.protocol import QDataStreamProtocol

gi = pygeoip.GeoIP('GeoIP.dat', pygeoip.MEMORY_CACHE)

@with_logger
class LobbyConnection(QObject):
    @timed()
    def __init__(self, loop, context=None, games: GameService=None, players=None, db=None, db_pool=None):
        super(LobbyConnection, self).__init__()
        self.loop = loop
        self.db = db
        self.db_pool = db_pool
        self.games = games
        self.players = players
        self.context = context
        self.ladderPotentialPlayers = []
        self.warned = False
        self._authenticated = False
        self.privkey = PRIVATE_KEY
        self.noSocket = False
        self.readingSocket = False
        self.player = None
        self.initPing = True
        self.ponged = False
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
                "INSERT INTO `table_mod`(`uid`, `name`, `version`, `author`, `ui`, `description`, `filename`, `icon`) VALUES (?,?,?,?,?,?,?,?)")
            query.addBindValue(uid)
            query.addBindValue(name)
            query.addBindValue(version)
            query.addBindValue(author)
            query.addBindValue(int(ui))
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

        if query.size() != 0:
            self.sendJSON(
                dict(command="notice", style="error", text="This map is already in the database !"))
            return

        writeFile = QFile(Config['content_path'] + "vault/maps/%s" % zipmap)

        if writeFile.open(QIODevice.WriteOnly):
            writeFile.write(fileDatas)
        writeFile.close()

        # Corrupt zipfile?
        if not zipfile.is_zipfile(Config['content_path'] + "vault/maps/%s" % zipmap):
            self.sendJSON(
                dict(command="notice", style="error", text="Cannot unzip map. Upload error ?"))
            return

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

        # We want the user to validate their email address before we create their account.
        #
        # We want to email them a link to click which will lead to their account being
        # created, but without storing any data on the server in the meantime.
        #
        # This is done by sending a link of the form:
        # *.php?data=E(username+password+email+expiry+nonce, K)&token=$VERIFICATION_CODE
        # where E(P, K) is a symmetric encryption function with plaintext P and secret key K,
        # and
        # VERIFICATION_CODE = sha256(username + password + email + expiry + K + nonce)
        #
        # The receiving php script decrypts `data`, verifies it (username still free? etc.),
        # recalculates the verification code, and creates the account if it matches up.
        #
        # As AES is not readily available for both Python and PHP, Blowfish is used.
        #
        # We thus avoid a SYN-flood-like attack on the registration system.

        expiry = str(time.time() + 3600 * 25)

        # Add nonce
        rng = Random.new()
        nonce = ''.join(choice(string.ascii_uppercase + string.digits) for _ in range(256))

        # The data payload we need on the PHP side
        plaintext = (login + "," + password + "," + email + "," + expiry + "," + nonce).encode('utf-8')

        bs = Blowfish.block_size
        paddinglen = bs - divmod(len(plaintext), bs)[1]
        padding = b',' * paddinglen

        plaintext += padding

        # Generate random IV of size one block.
        iv = rng.read(bs)
        cipher = Blowfish.new(VERIFICATION_SECRET_KEY, Blowfish.MODE_CBC, iv)
        ciphertext = cipher.encrypt(plaintext)

        # Generate the verification hash.
        verification = hashlib.sha256()
        verification.update(plaintext + VERIFICATION_HASH_SECRET.encode('utf-8'))
        verify_hex = verification.hexdigest()

        link = {'a': 'v', 'iv': base64.urlsafe_b64encode(iv), 'c': base64.urlsafe_b64encode(ciphertext), 'v': verify_hex}

        passwordLink = Config['app_url'] + "validateAccount.php?" + urllib.parse.urlencode(link)

        text = "Dear " + login + ",\n\n\
Please visit the following link to validate your FAF account:\n\
-----------------------\n\
" + passwordLink + "\n\
-----------------------\n\n\
Thanks,\n\
-- The FA Forever team"

        msg = MIMEText(text)


        msg['Subject'] = 'Forged Alliance Forever - Account validation'
        msg['From'] = email.utils.formataddr(('Forged Alliance Forever', MAIL_ADDRESS))
        msg['To'] = email.utils.formataddr((login, email))

        self._logger.debug("sending mail to " + email)
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

    def command_social_remove(self, message):
        query = "DELETE FROM "
        if "friend" in message:
            query += "friends WHERE idFriend"
            target = message['friend']
        elif "foe" in message:
            query += "foes WHERE idFoe"
            target = message['foe']
        else:
            self._logger.info("No-op social_remove ignored.")
            return

        query += " = %s AND idUser = %s"

        with (yield from self.db_pool) as conn:
            cursor = yield from conn.cursor()

            yield from cursor.execute(query, self.players.get_player_id(target).uuid, self.player.uuid)

    @timed()
    @asyncio.coroutine
    def command_social_add(self, message):
        query = "INSERT INTO "
        if "friend" in message:
            query += "friends (idUser, idFriend)"
            target = message['friend']
        elif "foe" in message:
            query += "foes (idUser, idFoe)"
            target = message['foe']
        else:
            self._logger.info("No-op social_add ignored.")
            return

        query += " values (%s,%s)"

        with (yield from self.db_pool) as conn:
            cursor = yield from conn.cursor()

            yield from cursor.execute(query, self.player.uuid, self.players.get_player_id(target))

    @timed()
    def command_admin(self, message):
        action = message['action']

        if self.player.admin:
            if action == "closeFA":
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

            elif action == "closelobby":
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

            elif action == "requestavatars":
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

            elif action == "remove_avatar":
                idavatar = message["idavatar"]
                iduser = message["iduser"]
                query = QSqlQuery(self.db)
                query.prepare("DELETE FROM `avatars` WHERE `idUser` = ? AND `idAvatar` = ?")
                query.addBindValue(iduser)
                query.addBindValue(idavatar)
                query.exec_()

            elif action == "list_avatar_users":
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

            elif action == "add_avatar":
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
        elif self.player.mod:
            if action == "join_channel":
                whos = message['users']
                channel = message['channel']

                for who in whos:
                    player = self.players.findByName(who)
                    if player:
                        player.lobbyThread.sendJSON(dict(command="social", autojoin=[channel]))

    @asyncio.coroutine
    def check_user_login(self, cursor, login, password):
        # TODO: Hash passwords server-side so the hashing actually *does* something.
        yield from cursor.execute("SELECT login.id as id,"
                                  "login.login as username,"
                                  "login.email as email,"
                                  "login.password as password,"
                                  "login.steamid as steamid,"
                                  "lobby_ban.reason as reason,"
                                  "lobby_admin.group as admin_group "
                                  "FROM login "
                                  "LEFT JOIN lobby_ban ON login.id = lobby_ban.idUser "
                                  "LEFT JOIN lobby_admin ON login.id = lobby_admin.user_id "
                                  "WHERE LOWER(login)=%s", login.lower())

        if cursor.rowcount != 1:
            self.sendJSON(dict(command="notice", style="error",
                               text="Login not found or password incorrect. They are case sensitive."))
            return

        player_id, real_username, self.email, dbPassword, steamid, ban_reason, permissionGroup = yield from cursor.fetchone()
        if dbPassword != password:
            self.sendJSON(dict(command="notice", style="error",
                               text="Login not found or password incorrect. They are case sensitive."))
            return

        if ban_reason != None:
            reason = "You are banned from FAF.\n Reason :\n " + ban_reason
            self.sendJSON(dict(command="notice", style="error", text=reason))
            return

        self._logger.debug("Login from: {}, {}, {}".format(player_id, self.email, self.session))
        self._authenticated = True

        return player_id, real_username, permissionGroup or 0, steamid

    def decodeUniqueId(self, string, login):
        try:
            query = QSqlQuery(self.db)

            query.prepare("SELECT id, steamid FROM login WHERE login.login = ?")
            query.addBindValue(login)
            steamLinked = query.size() == 1

            privkey = self.privkey

            message = (base64.b64decode(string))

            trailing = ord( message[0])

            message = message[1:]

            iv = (base64.b64decode(message[:24]))
            encoded = message[24:-40]
            key = (base64.b64decode(message[-40:]))

            AESkey = rsa.decrypt(key, privkey)

            # What the hell is this?
            cipher = AES.new(AESkey, AES.MODE_CBC, iv)
            DecodeAES = lambda c, e: c.decrypt(base64.b64decode(e))
            decoded = DecodeAES(cipher, encoded)[:-trailing]
            regexp = re.compile(r'[0-9a-zA-Z\\]("")')
            decoded = regexp.sub('"', decoded)
            decoded = decoded.replace("\\", "\\\\")
            regexp = re.compile('[^\x09\x0A\x0D\x20-\x7F]')
            decoded = regexp.sub('', decoded)
            jstring = json.loads(decoded)


            if str(jstring["session"]) != str(self.session) :
                self.sendJSON(dict(command="notice", style="error", text="Your session is corrupted. Try relogging"))
                return None

            machine = jstring["machine"]

            UUID = machine.get('UUID', 0)
            mem_SerialNumber = machine.get('mem_SerialNumber', 0)
            DeviceID = machine.get('DeviceID', 0)
            Manufacturer = machine.get('Manufacturer', 0)
            Name = machine.get('Name', 0)
            ProcessorId = machine.get('ProcessorId', 0)
            SMBIOSBIOSVersion = machine.get('SMBIOSBIOSVersion', 0)
            SerialNumber = machine.get('SerialNumber', 0)
            VolumeSerialNumber = machine.get('VolumeSerialNumber', 0)

            for i in  machine.values() :
                low = i.lower()
                if "vmware" in low or "virtual" in low or "innotek" in low or "qemu" in low or "parallels" in low or "bochs" in low :
                    if not steamLinked:
                        self.sendJSON(dict(command="notice", style="error", text="You need to link your account to Steam in order to use FAF in a Virtual Machine. You can contact the admin in the forums."))
                        return None

            m = hashlib.md5()
            m.update(str(UUID) + str(mem_SerialNumber) + str(DeviceID) + str(Manufacturer) + str(Name) + str(ProcessorId) + str(SMBIOSBIOSVersion) + str(SerialNumber) + str(VolumeSerialNumber))

            query.prepare("SELECT userid FROM `uniqueid` WHERE MD5( CONCAT( `uuid` , `mem_SerialNumber` , `deviceID` , `manufacturer` , `name` , `processorId` , `SMBIOSBIOSVersion` , `serialNumber` , `volumeSerialNumber` ) ) = ?")
            query.addBindValue(str(m.hexdigest()))
            if not query.exec_() :
                self.log.debug(query.lastQuery())
            if query.size() == 0 :
                query2 = QSqlQuery(self.db)
                query2.prepare("INSERT INTO `uniqueid` (`userid`, `uuid`, `mem_SerialNumber`, `deviceID`, `manufacturer`, `name`, `processorId`, `SMBIOSBIOSVersion`, `serialNumber`, `volumeSerialNumber`) VALUES ((SELECT id FROM login WHERE login.login = ?),?,?,?,?,?,?,?,?,?)")
                query2.addBindValue(login)
                query2.addBindValue(str(UUID))
                query2.addBindValue(str(mem_SerialNumber))
                query2.addBindValue(str(DeviceID))
                query2.addBindValue(str(Manufacturer))
                query2.addBindValue(str(Name))
                query2.addBindValue(str(ProcessorId))
                query2.addBindValue(str(SMBIOSBIOSVersion))
                query2.addBindValue(str(SerialNumber))
                query2.addBindValue(str(VolumeSerialNumber))
                if not query2.exec_() :
                    self.log.error("Failed query :")
                    self.log.error(query2.lastQuery())
                    self.log.error(query2.lastError())


            return m.hexdigest()

        except Exception as ex:
            self._logger.exception(ex)


    @asyncio.coroutine
    def command_hello(self, message):
        try:
            version = message['version']
            login = message['login'].strip()
            password = message['password']
            uniqueId = self.decodeUniqueId(message['unique_id'], login)

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

                player_id, login, permissionGroup, steamid = yield from self.check_user_login(cursor, login, password)

                # Login was not approved.
                if not player_id:
                    return

                if not self.steamid:
                    # If this id is associated with a different steam account, explode.
                    yield from cursor.execute("SELECT uniqueid FROM steam_uniqueid WHERE uniqueId = %s", uniqueId)
                    if cursor.rowcount > 0:
                        self.sendJSON(dict(command="notice", style="error",
                                           text="This computer has been used by a Steam account.<br>You have to link your account to Steam too in order to use it on this computer :<br>SteamLink: <a href='" +
                                                Config['app_url'] + "faf/steam.php'>" + Config[
                                                    'app_url'] + "faf/steam.php</a>"))
                        return

                    # check for another account using the same uniqueId as us.
                    yield from cursor.execute("SELECT id, login FROM login WHERE uniqueId = %s AND id != %s", uniqueId, player_id)

                    if cursor.rowcount > 0:
                        idFound, otherName = cursor.fetchone()

                        self._logger.debug("%i (%s) is a smurf of %s" % (self.player.id, login, otherName))
                        self.sendJSON(dict(command="notice", style="error",
                                           text="This computer is tied to this account : %s.<br>Multiple accounts are not allowed.<br>You can free this computer by logging in with that account (%s) on another computer.<br><br>Or Try SteamLink: <a href='" +
                                                Config['app_url'] + "faf/steam.php'>" +
                                                Config['app_url'] + "faf/steam.php</a>" % (
                                               otherName, otherName)))

                        yield from cursor.execute("INSERT INTO `smurf_table`(`origId`, `smurfId`) VALUES (%s,%s)", player_id, idFound)
                        return

                    yield from cursor.execute("UPDATE login SET ip = %s, uniqueId = %s WHERE id = %s", self.ip, uniqueId, player_id)
                else:
                    yield from cursor.execute("INSERT INTO `steam_uniqueid`(`uniqueid`) VALUES (%s)", uniqueId)

                # Update the user's IRC registration (why the fuck is this here?!)
                m = hashlib.md5()
                m.update(password.encode())
                passwordmd5 = m.hexdigest()
                m = hashlib.md5()
                # Since the password is hashed on the client, what we get at this point is really
                # md5(md5(sha256(password))). This is entirely insane.
                m.update(passwordmd5.encode())
                irc_pass = "md5:" + str(m.hexdigest())

                yield from cursor.execute("UPDATE anope.anope_db_NickCore SET pass = %s WHERE display = %s", irc_pass, login)

            self.player = Player(login=str(login),
                                 session=self.session,
                                 ip=self.ip,
                                 port=self.port,
                                 uuid=player_id,
                                 permissionGroup=permissionGroup,
                                 lobbyThread=self)

            # If the user has any authority, tell them about it.
            if self.player.mod:
                self.sendJSON({"command": "social", "power": permissionGroup})

            yield from self.players.fetch_player_data(self.player)

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
            query = QSqlQuery(self.db)
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
            LIMIT 1;" % (config.LADDER_SEASON, config.LADDER_SEASON, config.LADDER_SEASON, config.LADDER_SEASON))
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
                        "SELECT score, idUser FROM %s WHERE score <= ? and league = ? ORDER BY score DESC" % config.LADDER_SEASON)
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
                        "SELECT score, idUser FROM %s  WHERE league = ? ORDER BY score DESC" % config.LADDER_SEASON)
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

            self.sendJSON(dict(command="welcome", email=str(self.email), id=self.player.id, login=login))

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
                    container.addPlayer(self.player)
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

    @asyncio.coroutine
    def command_modvault(self, message):
        type = message["type"]

        with (yield from self.db_pool) as conn:
            cursor = yield from conn.cursor()
            if type == "start":
                yield from cursor.execute("SELECT uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon FROM table_mod ORDER BY likes DESC LIMIT 100")

                for i in range(0, cursor.rowcount):
                    uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon = cursor.fetchone()
                    date = date.toTime_t()
                    link = Config['content_url'] + "vault/" + filename
                    thumbstr = ""
                    if icon != "":
                        thumbstr = Config['content_url'] + "vault/mods_thumbs/" + urllib.parse.quote(icon)

                    out = dict(command="modvault_info", thumbnail=thumbstr, link=link, bugreports=[],
                               comments=[], description=description, played=played, likes=likes,
                               downloads=downloads, date=date, uid=uid, name=name, version=version, author=author,
                               ui=ui)
                    self.sendJSON(out)

            elif type == "like":
                canLike = True
                yield from cursor.execute("SELECT uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon, likers FROM `table_mod` WHERE uid = ? LIMIT 1")

                uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon, likerList = cursor.fetchone()
                date = date.toTime_t()
                link = Config['content_url'] + "vault/" + filename
                thumbstr = ""
                if icon != "":
                    thumbstr = Config['content_url'] + "vault/mods_thumbs/" + urllib.parse.quote(icon)

                out = dict(command="modvault_info", thumbnail=thumbstr, link=link, bugreports=[],
                           comments=[], description=description, played=played, likes=likes + 1,
                           downloads=downloads, date=date, uid=uid, name=name, version=version, author=author,
                           ui=ui)

                try:
                    likers = json.loads(likerList)
                    if self.player.id in likers:
                        canLike = False
                    else:
                        likers.append(self.player.id)
                except:
                    likers = []

                # TODO: Avoid sending all the mod info in the world just because we liked it?
                if canLike:
                    yield from cursor.execute("UPDATE `table_mod` SET likes=likes+1, likers=%s WHERE uid = %s", json.dumps(likers), uid)
                    self.sendJSON(out)

            elif type == "download":
                uid = message["uid"]
                yield from cursor.execute("UPDATE `table_mod` SET downloads=downloads+1 WHERE uid = %s", uid)
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
        for player in self.players.players:
            if player.lobbyThread:
                player.lobbyThread.removePotentialPlayer(self.player.login)
        self.players.remove_player(self.player)
