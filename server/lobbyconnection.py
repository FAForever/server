import asyncio

import hashlib
import cgi
import base64
import ipaddress
import json
import urllib.parse
import zipfile
import os
import shutil
import random
import re
from collections import defaultdict
from typing import List
from typing import Mapping
from typing import Optional

import datetime

import aiohttp
import pymysql
import rsa
import time
import smtplib
import string
import email
from email.mime.text import MIMEText

import semver
from Crypto import Random
from Crypto.Random.random import choice
from Crypto.Cipher import Blowfish
from Crypto.Cipher import AES
import pygeoip

import server
from server import GameConnection
from server.connectivity import Connectivity, ConnectivityState
from server.matchmaker import Search
from server.decorators import timed, with_logger
from server.games.game import GameState, VisibilityState
from server.players import Player, PlayerState
import server.db as db
from server.types import Address
from .game_service import GameService
from .player_service import PlayerService
from . import config
from .config import VERIFICATION_HASH_SECRET, VERIFICATION_SECRET_KEY, PRIVATE_KEY
from server.protocol import QDataStreamProtocol

gi = pygeoip.GeoIP('GeoIP.dat', pygeoip.MEMORY_CACHE)


class ClientError(Exception):
    """
    Represents a ClientError

    If recoverable is False, it is expected that the
    connection be terminated immediately.
    """
    def __init__(self, message, recoverable=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.recoverable = recoverable


class AuthenticationError(Exception):
    def __init__(self, message, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message


@with_logger
class LobbyConnection:
    @timed()
    def __init__(self, loop, context=None, games: GameService=None, players: PlayerService=None, db=None):
        super(LobbyConnection, self).__init__()
        self.loop = loop
        self.db = db
        self.game_service = games
        self.player_service = players  # type: PlayerService
        self.context = context
        self.ladderPotentialPlayers = []
        self.warned = False
        self._authenticated = False
        self.player = None  # type: Player
        self.game_connection = None  # type: GameConnection
        self.connectivity = None  # type: Connectivity
        self.leagueAvatar = None
        self.peer_address = None  # type: Optional[Address]
        self.session = int(random.randrange(0, 4294967295))
        self.protocol = None
        self._logger.debug("LobbyConnection initialized")
        self.search = None

    @property
    def authenticated(self):
        return self._authenticated

    @asyncio.coroutine
    def on_connection_made(self, protocol: QDataStreamProtocol, peername: Address):
        self.protocol = protocol
        self.peer_address = peername
        server.stats.incr("server.connections")

    def abort(self, logspam=""):
        if self.player:
            self._logger.warning("Client %s dropped. %s" % (self.player.login, logspam))
        else:
            self._logger.warning("Aborting %s. %s" % (self.peer_address.host, logspam))
        self._authenticated = False
        self.protocol.writer.close()

    def ensure_authenticated(self, cmd):
        if not self._authenticated:
            if cmd not in ['hello', 'ask_session', 'create_account', 'ping', 'pong']:
                self.abort("Message invalid for unauthenticated connection: %s" % cmd)
                return False
        return True

    async def on_message_received(self, message):
        """
        Dispatches incoming messages
        """
        try:
            cmd = message['command']
            if not self.ensure_authenticated(cmd):
                return
            target = message.get('target')
            if target == 'game':
                if not self.game_connection:
                    return
                await self.game_connection.handle_action(cmd, message.get('args', []))
                return
            elif target == 'connectivity':
                if not self.connectivity:
                    return
                await self.connectivity.on_message_received(message)
                return
            handler = getattr(self, 'command_{}'.format(cmd))
            if asyncio.iscoroutinefunction(handler):
                await handler(message)
            else:
                handler(message)
        except AuthenticationError as ex:
            self.protocol.send_message(
                {'command': 'authentication_failed',
                 'text': ex.message}
            )
        except ClientError as ex:
            self.protocol.send_message(
                {'command': 'notice',
                 'style': 'error',
                 'text': ex.message}
            )
            if not ex.recoverable:
                self.abort(ex.message)
        except (KeyError, ValueError) as ex:
            self._logger.exception(ex)
            self.abort("Garbage command: {}".format(message))
        except Exception as ex:
            self.protocol.send_message({'command': 'invalid'})
            self._logger.exception(ex)
            self.abort("Error processing command")

    def command_ping(self, msg):
        self.protocol.send_raw(self.protocol.pack_message('PONG'))

    def command_pong(self, msg):
        pass

    @staticmethod
    def generate_expiring_request(lifetime, plaintext):
        """
        Generate the parameters needed for an expiring email request with the given payload.
        Payload should be comma-delimited, and the consumer should expect to find and verify
        a timestamp and nonce appended to the given plaintext.
        """

        # Add nonce
        rng = Random.new()
        nonce = ''.join(choice(string.ascii_uppercase + string.digits) for _ in range(256))

        expiry = str(time.time() + lifetime)

        plaintext = (plaintext + "," + expiry + "," + nonce).encode('utf-8')

        # Pad the plaintext to the next full block with commas, because I can't be arsed to
        # write an actually clever parser.
        bs = Blowfish.block_size
        paddinglen = bs - (len(plaintext) % bs)
        plaintext += b',' * paddinglen

        # Generate random IV of size one block.
        iv = rng.read(bs)
        cipher = Blowfish.new(VERIFICATION_SECRET_KEY, Blowfish.MODE_CBC, iv)
        ciphertext = cipher.encrypt(plaintext)

        # Generate the verification hash.
        verification = hashlib.sha256()
        verification.update(plaintext + VERIFICATION_HASH_SECRET.encode('utf-8'))
        verify_hex = verification.hexdigest()

        return base64.urlsafe_b64encode(iv), base64.urlsafe_b64encode(ciphertext), verify_hex

    @asyncio.coroutine
    def command_create_account(self, message):
        login = message['login']
        user_email = message['email']
        password = message['password']

        username_pattern = re.compile(r"^[^,]{1,20}$")
        email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}$")

        def reply_no(error_msg):
            self.sendJSON({
                "command": "registration_response",
                "result": "FAILURE",
                "error": error_msg
            })

        if not email_pattern.match(user_email):
            reply_no("Please use a valid email address.")
            return

        if not username_pattern.match(login):
            reply_no("Please don't use \",\" in your username.")
            return

        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()
            yield from cursor.execute("SELECT id FROM `login` WHERE LOWER(`login`) = %s",
                                      (login.lower(),))
            if cursor.rowcount:
                reply_no("Sorry, that username is not available.")
                return

        if self.player_service.has_blacklisted_domain(user_email):
            # We don't like disposable emails.
            text = "Dear " + login + ",\n\n\
Please use a non-disposable email address.\n\n"
            yield from self.send_email(text, login, user_email, 'Forged Alliance Forever - Account validation')
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

        iv, ciphertext, verification_hex = self.generate_expiring_request(3600 * 25, login + "," + password + "," + user_email)


        link = {'a': 'v', 'iv': iv, 'c': ciphertext, 'v': verification_hex}

        passwordLink = urllib.parse.urljoin(config.APP_URL, "faf/validateAccount.php?" + urllib.parse.urlencode(link))

        text = "Dear " + login + ",\n\n\
Please visit the following link to validate your FAF account:\n\
-----------------------\n\
" + passwordLink + "\n\
-----------------------\n\n\
Thanks,\n\
-- The FA Forever team"

        yield from self.send_email(text, login, user_email, 'Forged Alliance Forever - Account validation')

        self.sendJSON(dict(command="notice", style="info",
                           text="A e-mail has been sent with the instructions to validate your account"))
        self._logger.debug("Sent mail")
        self.sendJSON(dict(command="registration_response", result="SUCCESS"))

    async def send_email(self, text, to_name, to_email, subject):
        msg = MIMEText(text)

        msg['Subject'] = subject
        msg['From'] = email.utils.formataddr(('Forged Alliance Forever', "admin@faforever.com"))
        msg['To'] = email.utils.formataddr((to_name, to_email))

        self._logger.debug("Sending mail to " + to_email)
        url = config.MANDRILL_API_URL + "/messages/send-raw.json"
        headers = {'content-type': 'application/json'}
        resp = await aiohttp.post(url,
                           data=json.dumps({
                "key": config.MANDRILL_API_KEY,
                "raw_message": msg.as_string(),
                "from_email": 'admin@faforever.com',
                "from_name": "Forged Alliance Forever",
                "to": [
                    to_email
                ],
                "async": False
            }),
            headers=headers)
        resp_text = await resp.text()
        self._logger.info("Mandrill response: {}".format(resp_text))

    @timed()
    def send_tutorial_section(self):
        reply = []

        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()

            # Can probably replace two queries with one here if we're smart enough.
            yield from cursor.execute("SELECT `section`,`description` FROM `tutorial_sections`")

            for i in range(0, cursor.rowcount):
                section, description = yield from cursor.fetchone()
                reply.append( {"command": "tutorials_info", "section": section, "description": description})

            yield from cursor.execute("SELECT tutorial_sections.`section`, `name`, `url`, `tutorials`.`description`, `map` FROM `tutorials` LEFT JOIN  tutorial_sections ON tutorial_sections.id = tutorials.section ORDER BY `tutorials`.`section`, name")

            for i in range(0, cursor.rowcount):
                section, tutorial_name, url, description, map_name = yield from cursor.fetchone()
                reply.append({"command": "tutorials_info", "tutorial": tutorial_name, "url": url,
                              "tutorial_section": section, "description": description,
                              "mapname": map_name})

        self.protocol.send_messages(reply)

    async def send_coop_maps(self):
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            await cursor.execute("SELECT name, description, filename, type, id FROM `coop_map`")

            maps = []
            for i in range(0, cursor.rowcount):
                name, description, filename, type, id = await cursor.fetchone()
                jsonToSend = {"command": "coop_info", "name": name, "description": description,
                              "filename": filename, "featured_mod": "coop"}
                if type == 0:
                    jsonToSend["type"] = "FA Campaign"
                elif type == 1:
                    jsonToSend["type"] = "Aeon Vanilla Campaign"
                elif type == 2:
                    jsonToSend["type"] = "Cybran Vanilla Campaign"
                elif type == 3:
                    jsonToSend["type"] = "UEF Vanilla Campaign"
                else:
                    # Don't sent corrupt data to the client...
                    self._logger.error("Unknown coop type!")
                    return
                jsonToSend["uid"] = id
                maps.append(jsonToSend)

        self.protocol.send_messages(maps)

    @timed
    def send_mod_list(self):
        self.protocol.send_messages(self.game_service.all_game_modes())

    @timed()
    def send_game_list(self):
        self.sendJSON({
            'command': 'game_info',
            'games': [game.to_dict() for game in self.game_service.all_games]
        })

    @asyncio.coroutine
    def command_social_remove(self, message):
        if "friend" in message:
            target_id = message['friend']
        elif "foe" in message:
            target_id = message['foe']
        else:
            self.abort("No-op social_remove.")
            return

        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()

            yield from cursor.execute("DELETE FROM friends_and_foes WHERE user_id = %s AND subject_id = %s",
                                      (self.player.id, target_id))

    @timed()
    @asyncio.coroutine
    def command_social_add(self, message):
        if "friend" in message:
            status = "FRIEND"
            target_id = message['friend']
        elif "foe" in message:
            status = "FOE"
            target_id = message['foe']
        else:
            return

        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()

            yield from cursor.execute("INSERT INTO friends_and_foes(user_id, subject_id, `status`) VALUES(%s, %s, %s)",
                                      (self.player.id, target_id, status))

    def kick(self, message=None):
        self.sendJSON(dict(command="notice", style="kick"))
        if message:
            self.sendJSON(dict(command="notice", style="info",
                                                  text=message))
        self.abort()

    def send_updated_achievements(self, updated_achievements):
        self.sendJSON(dict(command="updated_achievements", updated_achievements=updated_achievements))

    @asyncio.coroutine
    def command_admin(self, message):
        action = message['action']

        if self.player.admin:
            if action == "closeFA":
                player = self.player_service[message['user_id']]
                if player:
                    self._logger.info('Administrative action: {} closed game for {}'.format(self.player, player))
                    player.lobby_connection.sendJSON(dict(command="notice", style="kill"))
                    player.lobby_connection.sendJSON(dict(command="notice", style="info",
                                       text=("Your game was closed by an administrator ({admin_name}). "
                                             "Please refer to our rules for the lobby/game here {rule_link}."
                                       .format(admin_name=self.player.login,
                                               rule_link=config.RULE_LINK))))

            elif action == "closelobby":
                player = self.player_service[message['user_id']]
                if player:
                    self._logger.info('Administrative action: {} closed client for {}'.format(self.player, player))
                    player.lobby_connection.kick(
                        message=("Your client was closed by an administrator ({admin_name}). "
                         "Please refer to our rules for the lobby/game here {rule_link}."
                          .format(admin_name=self.player.login,
                                  rule_link=config.RULE_LINK)))

            elif action == "requestavatars":
                with (yield from db.db_pool) as conn:
                    cursor = yield from conn.cursor()
                    yield from cursor.execute("SELECT url, tooltip FROM `avatars_list`")

                    avatars = yield from cursor.fetchall()
                    data = {"command": "admin", "avatarlist": []}
                    for url, tooltip in avatars:
                        data['avatarlist'].append({"url": url, "tooltip": tooltip})

                    self.sendJSON(data)

            elif action == "remove_avatar":
                idavatar = message["idavatar"]
                iduser = message["iduser"]
                with (yield from db.db_pool) as conn:
                    cursor = yield from conn.cursor()
                    yield from cursor.execute("DELETE FROM `avatars` "
                                              "WHERE `idUser` = %s "
                                              "AND `idAvatar` = %s", (idavatar, iduser))

            elif action == "add_avatar":
                who = message['user']
                avatar = message['avatar']

                with (yield from db.db_pool) as conn:
                    cursor = yield from conn.cursor()
                    if avatar is None:
                        yield from cursor.execute(
                            "DELETE FROM `avatars` "
                            "WHERE `idUser` = "
                            "(SELECT `id` FROM `login` WHERE `login`.`login` = %s)", (who, ))
                    else:
                        yield from cursor.execute(
                            "INSERT INTO `avatars`(`idUser`, `idAvatar`) "
                            "VALUES ((SELECT id FROM login WHERE login.login = %s),"
                            "(SELECT id FROM avatars_list WHERE avatars_list.url = %s)) "
                            "ON DUPLICATE KEY UPDATE `idAvatar` = (SELECT id FROM avatars_list WHERE avatars_list.url = %s)",
                            (who, avatar, avatar))
        elif self.player.mod:
            if action == "join_channel":
                user_ids = message['user_ids']
                channel = message['channel']

                for user_id in user_ids:
                    player = self.player_service[message[user_id]]
                    if player:
                        player.lobby_connection.sendJSON(dict(command="social", autojoin=[channel]))

    async def check_user_login(self, cursor, login, password):
        # TODO: Hash passwords server-side so the hashing actually *does* something.
        await cursor.execute("SELECT login.id as id,"
                                  "login.login as username,"
                                  "login.password as password,"
                                  "login.steamid as steamid,"
                                  "lobby_ban.reason as reason,"
                                  "lobby_ban.expires_at as expires_at "
                                  "FROM login "
                                  "LEFT JOIN lobby_ban ON login.id = lobby_ban.idUser "
                                  "WHERE LOWER(login)=%s", (login.lower(), ))

        if cursor.rowcount != 1:
            raise AuthenticationError("Login not found or password incorrect. They are case sensitive.")

        player_id, real_username, dbPassword, steamid, ban_reason, ban_expiry = await cursor.fetchone()
        if dbPassword != password:
            raise AuthenticationError("Login not found or password incorrect. They are case sensitive.")

        if ban_reason is not None and datetime.datetime.now() < ban_expiry:
            raise ClientError("You are banned from FAF.\n Reason :\n {}".format(ban_reason))

        self._logger.debug("Login from: {}, {}, {}".format(player_id, login, self.session))

        return player_id, real_username, steamid

    def decodeUniqueId(self, serialized_uniqueid):
        try:
            message = (base64.b64decode(serialized_uniqueid)).decode('utf-8')

            trailing = ord(message[0])

            message = message[1:]

            iv = (base64.b64decode(message[:24]))
            encoded = message[24:-40]
            key = (base64.b64decode(message[-40:]))

            AESkey = rsa.decrypt(key, PRIVATE_KEY)

            # What the hell is this?
            cipher = AES.new(AESkey, AES.MODE_CBC, iv)
            DecodeAES = lambda c, e: c.decrypt(base64.b64decode(e)).decode('utf-8')
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

            UUID = str(machine.get('UUID', 0)).encode()
            mem_SerialNumber = str(machine.get('mem_SerialNumber', 0)).encode()
            DeviceID = str(machine.get('DeviceID', 0)).encode()
            Manufacturer = str(machine.get('Manufacturer', 0)).encode()
            Name = str(machine.get('Name', 0)).encode()
            ProcessorId = str(machine.get('ProcessorId', 0)).encode()
            SMBIOSBIOSVersion = str(machine.get('SMBIOSBIOSVersion', 0)).encode()
            SerialNumber = str(machine.get('SerialNumber', 0)).encode()
            VolumeSerialNumber = str(machine.get('VolumeSerialNumber', 0)).encode()

            for i in machine.values() :
                if not hasattr(i, "lower"): continue
                low = i.lower()
                if "vmware" in low or "virtual" in low or "innotek" in low or "qemu" in low or "parallels" in low or "bochs" in low :
                    return "VM"

            m = hashlib.md5()
            m.update(UUID + mem_SerialNumber + DeviceID + Manufacturer + Name + ProcessorId + SMBIOSBIOSVersion + SerialNumber + VolumeSerialNumber)

            return m.hexdigest(), (UUID, mem_SerialNumber, DeviceID, Manufacturer, Name, ProcessorId, SMBIOSBIOSVersion, SerialNumber, VolumeSerialNumber)
        except Exception as ex:
            self._logger.exception(ex)

    async def validate_unique_id(self, cursor, player_id, steamid, encoded_unique_id):
        # Accounts linked to steam are exempt from uniqueId checking.
        if steamid:
            return True

        uid_hash, hardware_info = self.decodeUniqueId(encoded_unique_id)

        # VM users must use steam.
        if uid_hash == "VM":
            self.sendJSON(dict(command="notice", style="error", text="You need to link your account to Steam in order to use FAF in a Virtual Machine. You can contact an admin on the forums."))
            return False

        # check for other accounts using the same uniqueId as us.
        await cursor.execute("SELECT user_id FROM unique_id_users WHERE uniqueid_hash = %s", (uid_hash, ))

        users = []
        for id, in await cursor.fetchall():
            users.append(id)

        # Is the user we're logging in with not currently associated with this uid?
        if player_id not in users:
            # Do we have a spare slot into which we can allocate this new account?
            if len(users) > 1:
                #self.sendJSON(dict(command="notice", style="error",
                #                   text="This computer is already associated with too many FAF accounts.<br><br>You might want to try linking your account with Steam: <a href='" +
                #                        config.APP_URL + "/faf/steam.php'>" +
                #                        config.APP_URL + "/faf/steam.php</a>"))
                self._logger.warning("UID hit: {}: {}".format(player_id, uid_hash))

            # Is this a uuid we have never seen before?
            if len(users) == 0:
                # Store its component parts in the table for doing that sort of thing. (just for
                # human-reading, really)
                try:
                    await cursor.execute("INSERT INTO `uniqueid` (`hash`, `uuid`, `mem_SerialNumber`, `deviceID`, `manufacturer`, `name`, `processorId`, `SMBIOSBIOSVersion`, `serialNumber`, `volumeSerialNumber`)"
                                         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (uid_hash, *hardware_info))
                except Exception as e:
                    self._logger.warning("UID dupe: {}: {}".format(player_id, uid_hash))

            # Associate this account with this hardware hash.
            try:
                await cursor.execute("INSERT INTO unique_id_users(user_id, uniqueid_hash) VALUES(%s, %s)", (player_id, uid_hash))
            except Exception as e:
                self._logger.warning("UID association dupe: {}: {}".format(player_id, uid_hash))

        # TODO: Mildly unpleasant
        await cursor.execute("UPDATE login SET ip = %s WHERE id = %s", (self.peer_address.host, player_id))

        return True

    def check_version(self, message):
        versionDB, updateFile = self.player_service.client_version_info
        update_msg = dict(command="update",
                          update=updateFile,
                          new_version=versionDB)

        if 'version' not in message or 'user_agent' not in message:
            update_msg['command'] = 'welcome'
            # For compatibility with 0.10.x updating mechanism
            self.sendJSON(update_msg)
            return False

        version = message.get('version')

        # Check their client is reporting the right version number.
        if message.get('user_agent', None) != 'downlords-faf-client':
            try:
                if "-" in version:
                    version = version.split('-')[0]
                if "+" in version:
                    version = version.split('+')[0]
                if semver.compare(versionDB, version) > 0:
                    self.sendJSON(update_msg)
                    return False
            except ValueError:
                self.sendJSON(update_msg)
                return False
        return True

    async def command_hello(self, message):
        login = message['login'].strip()
        password = message['password']

        # Check their client is reporting the right version number.
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()
            player_id, login, steamid = await self.check_user_login(cursor, login, password)
            server.stats.incr('user.logins')
            server.stats.gauge('users.online', len(self.player_service))

            if not self.player_service.is_uniqueid_exempt(player_id):
                # UniqueID check was rejected (too many accounts or tamper-evident madness)
                uniqueid_pass = await self.validate_unique_id(cursor, player_id, steamid, message['unique_id'])
                if not uniqueid_pass:
                    return

            # Update the user's IRC registration (why the fuck is this here?!)
            m = hashlib.md5()
            m.update(password.encode())
            passwordmd5 = m.hexdigest()
            m = hashlib.md5()
            # Since the password is hashed on the client, what we get at this point is really
            # md5(md5(sha256(password))). This is entirely insane.
            m.update(passwordmd5.encode())
            irc_pass = "md5:" + str(m.hexdigest())

            try:
                await cursor.execute("UPDATE anope.anope_db_NickCore SET pass = %s WHERE display = %s", (irc_pass, login))
            except (pymysql.OperationalError, pymysql.ProgrammingError):
                self._logger.info("Failure updating NickServ password for {}".format(login))

        permission_group = self.player_service.get_permission_group(player_id)
        self.player = Player(login=str(login),
                             session=self.session,
                             ip=self.peer_address.host,
                             port=None,
                             id=player_id,
                             permissionGroup=permission_group,
                             lobby_connection=self)
        self.connectivity = Connectivity(self, self.peer_address.host, self.player)

        if self.player.id in self.player_service and self.player_service[self.player.id].lobby_connection:
            old_conn = self.player_service[self.player.id].lobby_connection
            old_conn.send_warning("You have been signed out because you signed in elsewhere.", fatal=True)

        await self.player_service.fetch_player_data(self.player)

        self.player_service[self.player.id] = self.player
        self._authenticated = True

        # Country
        # -------

        country = gi.country_code_by_addr(self.peer_address.host)
        if country is not None:
            self.player.country = str(country)

        ## AVATARS
        ## -------------------
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT url, tooltip FROM `avatars` "
                "LEFT JOIN `avatars_list` ON `idAvatar` = `avatars_list`.`id` "
                "WHERE `idUser` = %s AND `selected` = 1", (self.player.id, ))
            avatar = await cursor.fetchone()
            if avatar:
                url, tooltip = avatar
                self.player.avatar = {"url": url, "tooltip": tooltip}

        self.sendJSON(dict(command="welcome", id=self.player.id, login=login))

        # Tell player about everybody online
        self.sendJSON(
            {
                "command": "player_info",
                "players": [player.to_dict() for player in self.player_service]
            }
        )
        # Tell everyone else online about us
        self.player_service.mark_dirty(self.player)

        friends = []
        foes = []
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()
            await cursor.execute("SELECT `subject_id`, `status` "
                                 "FROM friends_and_foes WHERE user_id = %s", (self.player.id,))

            for target_id, status in await cursor.fetchall():
                if status == "FRIEND":
                    friends.append(target_id)
                else:
                    foes.append(target_id)

        self.player.friends = set(friends)
        self.player.foes = set(foes)

        self.send_mod_list()
        self.send_game_list()
        self.send_tutorial_section()

        channels = []
        if self.player.mod:
            channels.append("#moderators")

        if self.player.clan is not None:
            channels.append("#%s_clan" % self.player.clan)

        jsonToSend = {"command": "social", "autojoin": channels, "channels": channels, "friends": friends, "foes": foes, "power": permission_group}
        self.sendJSON(jsonToSend)

    @timed
    def command_ask_session(self, message):
        if self.check_version(message):
            self.sendJSON({
                "command": "session",
                "session": self.session
            })

    @asyncio.coroutine
    def command_avatar(self, message):
        action = message['action']

        if action == "list_avatar":
            avatarList = []

            with (yield from db.db_pool) as conn:
                cursor = yield from conn.cursor()
                yield from cursor.execute(
                    "SELECT url, tooltip FROM `avatars` "
                    "LEFT JOIN `avatars_list` ON `idAvatar` = `avatars_list`.`id` WHERE `idUser` = %s", (self.player.id, ))

                avatars = yield from cursor.fetchall()
                for url, tooltip in avatars:
                    avatar = {"url": url, "tooltip": tooltip}
                    avatarList.append(avatar)

                if len(avatarList) > 0:
                    jsonToSend = {"command": "avatar", "avatarlist": avatarList}
                    self.sendJSON(jsonToSend)

        elif action == "select":
            avatar = message['avatar']

            with (yield from db.db_pool) as conn:
                cursor = yield from conn.cursor()
                yield from cursor.execute(
                    "UPDATE `avatars` SET `selected` = 0 WHERE `idUser` = %s", (self.player.id, ))
                if avatar is not None:
                    yield from cursor.execute(
                        "UPDATE `avatars` SET `selected` = 1 WHERE `idAvatar` ="
                        "(SELECT id FROM avatars_list WHERE avatars_list.url = %s) and "
                        "`idUser` = %s", (avatar, self.player.id))
        else:
            raise KeyError('invalid action')

    @property
    def able_to_launch_game(self):
        return self.connectivity.result

    @timed
    def command_game_join(self, message):
        """
        We are going to join a game.
        """
        assert isinstance(self.player, Player)
        if not self.able_to_launch_game:
            raise ClientError("You are already in a game or haven't run the connectivity test yet")

        if self.connectivity.result.state == ConnectivityState.STUN:
            self.connectivity.relay_address = Address(*message['relay_address'])

        uuid = message['uid']
        port = message['gameport']
        password = message.get('password', None)

        self._logger.debug("joining: {}:{} with pw: {}".format(uuid, port, password))
        try:
            game = self.game_service[uuid]
            if not game or game.state != GameState.LOBBY:
                self._logger.debug("Game not in lobby state: {}".format(game))
                self.sendJSON(dict(command="notice", style="info", text="The game you are trying to join is not ready."))
                return

            if game.password != password:
                self.sendJSON(dict(command="notice", style="info", text="Bad password (it's case sensitive)"))
                return

            self.launch_game(game, port, False)
        except KeyError:
            self.sendJSON(dict(command="notice", style="info", text="The host has left the game"))


    @asyncio.coroutine
    def command_game_matchmaking(self, message):
        mod = message.get('mod', 'ladder1v1')
        port = message.get('gameport', None)
        state = message['state']

        if not self.able_to_launch_game:
            raise ClientError("You are already in a game or are otherwise having connection problems. Please report this issue using HELP -> Tech support.")

        if state == "stop":
            if self.search:
                self._logger.info("{} stopped searching for ladder: {}".format(self.player, self.search))
                self.search.cancel()
            return

        if self.connectivity.result.state == ConnectivityState.STUN:
            self.connectivity.relay_address = Address(*message['relay_address'])

        if port:
            self.player.game_port = port

        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()
            yield from cursor.execute("SELECT id FROM matchmaker_ban WHERE `userid` = %s", (self.player.id))
            if cursor.rowcount > 0:
                self.sendJSON(dict(command="notice", style="error",
                                   text="You are banned from the matchmaker. Contact an admin to have the reason."))
                return

        if mod == "ladder1v1":
            if state == "start":
                if self.search:
                    self.search.cancel()
                assert self.player is not None
                self.search = Search(self.player)
                self.player.faction = message['faction']

                self.game_service.ladder_service.inform_player(self.player)

                self._logger.info("{} is searching for ladder: {}".format(self.player, self.search))
                asyncio.ensure_future(self.player_service.ladder_queue.search(self.player, search=self.search))

    def command_coop_list(self, message):
        """ Request for coop map list"""
        asyncio.ensure_future(self.send_coop_maps())

    @timed()
    def command_game_host(self, message):
        if not self.able_to_launch_game:
            raise ClientError("You are already in a game or haven't run the connectivity test yet")

        if self.connectivity.result.state == ConnectivityState.STUN:
            self.connectivity.relay_address = Address(*message['relay_address'])

        assert isinstance(self.player, Player)

        title = cgi.escape(message.get('title', ''))
        port = message.get('gameport')
        visibility = VisibilityState.from_string(message.get('visibility'))
        if not isinstance(visibility, VisibilityState):
            # Protocol violation.
            self.abort("%s sent a nonsense visibility code: %s" % (self.player.login, message.get('visibility')))
            return

        mod = message.get('mod')
        try:
            title.encode('ascii')
        except UnicodeEncodeError:
            self.sendJSON(dict(command="notice", style="error", text="Non-ascii characters in game name detected."))
            return

        mapname = message.get('mapname')
        password = message.get('password')

        game = self.game_service.create_game(**{
            'visibility': VisibilityState.to_string(visibility),
            'game_mode': mod.lower(),
            'host': self.player,
            'name': title if title else self.player.login,
            'mapname': mapname,
            'password': password
        })
        self.launch_game(game, port, True)
        server.stats.incr('game.hosted')

    def launch_game(self, game, port, is_host=False, use_map=None):
        # FIXME: Setting up a ridiculous amount of cyclic pointers here
        if self.game_connection:
            self.game_connection.abort("Player launched a new game")
        self.game_connection = GameConnection(self.loop,
                                              self,
                                              self.player_service,
                                              self.game_service)
        self.game_connection.player = self.player
        self.player.game_connection = self.game_connection
        self.game_connection.game = game
        if is_host:
            game.host = self.player

        self.player.state = PlayerState.HOSTING if is_host else PlayerState.JOINING
        self.player.game = game
        self.player.game_port = port
        cmd = {"command": "game_launch",
                       "mod": game.game_mode,
                       "uid": game.id,
                       "args": ["/numgames " + str(self.player.numGames)]}
        if use_map:
            cmd['mapname'] = use_map
        self.sendJSON(cmd)

    @asyncio.coroutine
    def command_modvault(self, message):
        type = message["type"]

        with (yield from db.db_pool) as conn:
            cursor = yield from conn.cursor()
            if type == "start":
                yield from cursor.execute("SELECT uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon FROM table_mod ORDER BY likes DESC LIMIT 100")

                for i in range(0, cursor.rowcount):
                    uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon = yield from cursor.fetchone()
                    link = urllib.parse.urljoin(config.CONTENT_URL, "faf/vault/" + filename)
                    thumbstr = ""
                    if icon != "":
                        thumbstr = urllib.parse.urljoin(config.CONTENT_URL, "faf/vault/mods_thumbs/" + urllib.parse.quote(icon))

                    out = dict(command="modvault_info", thumbnail=thumbstr, link=link, bugreports=[],
                               comments=[], description=description, played=played, likes=likes,
                               downloads=downloads, date=int(date.timestamp()), uid=uid, name=name, version=version, author=author,
                               ui=ui)
                    self.sendJSON(out)

            elif type == "like":
                canLike = True
                uid = message['uid']
                yield from cursor.execute("SELECT uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon, likers FROM `table_mod` WHERE uid = %s LIMIT 1", (uid,))

                uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon, likerList = yield from cursor.fetchone()
                link = urllib.parse.urljoin(config.CONTENT_URL, "faf/vault/" + filename)
                thumbstr = ""
                if icon != "":
                    thumbstr = urllib.parse.urljoin(config.CONTENT_URL, "faf/vault/mods_thumbs/" + urllib.parse.quote(icon))

                out = dict(command="modvault_info", thumbnail=thumbstr, link=link, bugreports=[],
                           comments=[], description=description, played=played, likes=likes + 1,
                           downloads=downloads, date=int(date.timestamp()), uid=uid, name=name, version=version, author=author,
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
            else:
                raise ValueError('invalid type argument')

    def send_warning(self, message: str, fatal: bool=False):
        """
        Display a warning message to the client
        :param message: Warning message to display
        :param fatal: Whether or not the warning is fatal.
                      If the client receives a fatal warning it should disconnect
                      and not attempt to reconnect.
        :return: None
        """
        self.sendJSON({'command': 'notice',
                       'style': 'info' if not fatal else 'error',
                       'text': message})
        if fatal:
            self.abort(message)

    def send(self, message):
        """

        :param message:
        :return:
        """
        self._logger.debug(">>: {}".format(message))
        self.protocol.send_message(message)

    async def drain(self):
        await self.protocol.drain()

    def sendJSON(self, data_dictionary):
        """
        Deprecated alias for send
        """
        self.send(data_dictionary)

    async def on_connection_lost(self):
        async def nopdrain(message):
            return
        self.drain = nopdrain
        self.send = lambda m: None
        if self.game_connection:
            await self.game_connection.on_connection_lost()
        if self.search and not self.search.done():
            self.search.cancel()
        if self.player:
            self.player_service.remove_player(self.player)
