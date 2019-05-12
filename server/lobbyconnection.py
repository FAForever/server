import asyncio
import datetime
import hashlib
import html
import json
import random
import urllib.parse
import urllib.request
from typing import Optional

import requests

import humanize
import pymysql
import semver
import server
import server.db as db
from sqlalchemy import and_, func, text

from . import config
from .abc.base_game import GameConnectionState
from .config import FAF_POLICY_SERVER_BASE_URL, TRACE, TWILIO_TTL
from .db.models import ban, friends_and_foes
from .decorators import timed, with_logger
from .game_service import GameService
from .gameconnection import GameConnection
from .games import GameState, VisibilityState
from .geoip_service import GeoIpService
from .ice_servers.coturn import CoturnHMAC
from .ice_servers.nts import TwilioNTS
from .matchmaker import Search
from .player_service import PlayerService
from .players import Player, PlayerState
from .protocol import QDataStreamProtocol
from .types import Address
from .ladder_service import LadderService


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
class LobbyConnection():
    @timed()
    def __init__(
        self,
        games: GameService,
        players: PlayerService,
        nts_client: Optional[TwilioNTS],
        geoip: GeoIpService,
        ladder_service: LadderService
    ):
        self.geoip_service = geoip
        self.game_service = games
        self.player_service = players
        self.nts_client = nts_client
        self.coturn_generator = CoturnHMAC()
        self.ladder_service = ladder_service
        self._authenticated = False
        self.player = None  # type: Player
        self.game_connection = None  # type: GameConnection
        self.peer_address = None  # type: Optional[Address]
        self.session = int(random.randrange(0, 4294967295))
        self.protocol = None
        self.user_agent = None

        self._attempted_connectivity_test = False

        self._logger.debug("LobbyConnection initialized")

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
        if self.game_connection:
            self.game_connection.abort()
            self.game_connection = None
        self._authenticated = False
        self.protocol.writer.close()

        if self.player:
            self.player_service.remove_player(self.player)
            self.player = None

    def ensure_authenticated(self, cmd):
        if not self._authenticated:
            if cmd not in ['hello', 'ask_session', 'create_account', 'ping', 'pong', 'Bottleneck']:  # Bottleneck is sent by the game during reconnect
                self.abort("Message invalid for unauthenticated connection: %s" % cmd)
                return False
        return True

    async def on_message_received(self, message):
        """
        Dispatches incoming messages
        """
        self._logger.log(TRACE, "<<: %s", message)

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

            if target == 'connectivity' and message.get('command') == 'InitiateTest':
                self._attempted_connectivity_test = True
                raise ClientError("Your client version is no longer supported. Please update to the newest version: https://faforever.com")
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
        except Exception as ex:  # pragma: no cover
            self.protocol.send_message({'command': 'invalid'})
            self._logger.exception(ex)
            self.abort("Error processing command")

    def command_ping(self, msg):
        self.protocol.send_raw(self.protocol.pack_message('PONG'))

    def command_pong(self, msg):
        pass

    @asyncio.coroutine
    def command_create_account(self, message):
        raise ClientError("FAF no longer supports direct registration. Please use the website to register.", recoverable=True)

    async def send_coop_maps(self):
        async with db.engine.acquire() as conn:
            result = await conn.execute("SELECT name, description, filename, type, id FROM `coop_map`")

            maps = []
            async for row in result:
                json_to_send = {
                    "command": "coop_info",
                    "name": row["name"],
                    "description": row["description"],
                    "filename": row["filename"],
                    "featured_mod": "coop"
                }
                campaigns = [
                    "FA Campaign",
                    "Aeon Vanilla Campaign",
                    "Cybran Vanilla Campaign",
                    "UEF Vanilla Campaign",
                    "Custom Missions"
                ]
                if row["type"] < len(campaigns):
                    json_to_send["type"] = campaigns[row["type"]]
                else:
                    # Don't sent corrupt data to the client...
                    self._logger.error("Unknown coop type!")
                    continue
                json_to_send["uid"] = row["id"]
                maps.append(json_to_send)

        self.protocol.send_messages(maps)

    @timed
    def send_mod_list(self):
        self.protocol.send_messages(self.game_service.all_game_modes())

    @timed()
    def send_game_list(self):
        self.sendJSON({
            'command': 'game_info',
            'games': [game.to_dict() for game in self.game_service.open_games]
        })

    async def command_social_remove(self, message):
        if "friend" in message:
            subject_id = message["friend"]
        elif "foe" in message:
            subject_id = message["foe"]
        else:
            self.abort("No-op social_remove.")
            return

        async with db.engine.acquire() as conn:
            await conn.execute(friends_and_foes.delete().where(and_(
                friends_and_foes.c.user_id == self.player.id,
                friends_and_foes.c.subject_id == subject_id
            )))

    async def command_social_add(self, message):
        if "friend" in message:
            status = "FRIEND"
            subject_id = message["friend"]
        elif "foe" in message:
            status = "FOE"
            subject_id = message["foe"]
        else:
            return

        async with db.engine.acquire() as conn:
            await conn.execute(friends_and_foes.insert().values(
                user_id=self.player.id,
                status=status,
                subject_id=subject_id,
            ))

    def kick(self, message=None):
        self.sendJSON(dict(command="notice", style="kick"))
        if message:
            self.sendJSON(dict(command="notice", style="info",
                                                  text=message))
        self.abort()

    def send_updated_achievements(self, updated_achievements):
        self.sendJSON(dict(command="updated_achievements", updated_achievements=updated_achievements))

    async def command_admin(self, message):
        action = message['action']

        if self.player.admin:
            if action == "closeFA":
                player = self.player_service[message['user_id']]
                if player:
                    self._logger.warning('Administrative action: %s closed game for %s', self.player, player)
                    player.lobby_connection.sendJSON(dict(command="notice", style="kill"))
                    player.lobby_connection.sendJSON(dict(command="notice", style="info",
                                       text=("Your game was closed by an administrator ({admin_name}). "
                                             "Please refer to our rules for the lobby/game here {rule_link}."
                                       .format(admin_name=self.player.login,
                                               rule_link=config.RULE_LINK))))

            elif action == "closelobby":
                player = self.player_service[message['user_id']]
                ban_fail = None
                if player:
                    if 'ban' in message:
                        reason = message['ban'].get('reason', 'Unspecified')
                        duration = int(message['ban'].get('duration', 1))
                        period = message['ban'].get('period', 'DAY').upper()
                        self._logger.warning('Administrative action: %s closed client for %s with %s ban (Reason: %s)', self.player, player, duration, reason)
                        async with db.engine.acquire() as conn:
                            try:
                                result = await conn.execute("SELECT reason from lobby_ban WHERE idUser=%s AND expires_at > NOW()", (message['user_id']))

                                row = await result.fetchone()
                                if row:
                                    ban_fail = row[0]
                                else:
                                    if period not in ["DAY", "WEEK", "MONTH"]:
                                        self._logger.warning('Tried to ban player with invalid period')
                                        raise ClientError(f"Period '{period}' is not allowed!")

                                    # NOTE: Text formatting in sql string is only ok because we just checked it's value
                                    await conn.execute(
                                        ban.insert().values(
                                            player_id=player.id,
                                            author_id=self.player.id,
                                            reason=reason,
                                            expires_at=func.date_add(
                                                func.now(),
                                                text(f"interval :duration {period}")
                                            ),
                                            level='GLOBAL'
                                        ),
                                        duration=duration
                                    )
                            except pymysql.MySQLError as e:
                                raise ClientError('Your ban attempt upset the database: {}'.format(e))
                    else:
                        self._logger.warning('Administrative action: %s closed client for %s', self.player, player)
                    player.lobby_connection.kick(
                        message=("You were kicked from FAF by an administrator ({admin_name}). "
                         "Please refer to our rules for the lobby/game here {rule_link}."
                          .format(admin_name=self.player.login,
                                  rule_link=config.RULE_LINK)))
                    if ban_fail:
                        raise ClientError("Kicked the player, but he was already banned!")

            elif action == "requestavatars":
                async with db.engine.acquire() as conn:
                    result = await conn.execute("SELECT url, tooltip FROM `avatars_list`")

                    data = {"command": "admin", "avatarlist": []}
                    async for row in result:
                        data['avatarlist'].append({
                            "url": row["url"],
                            "tooltip": row["tooltip"]
                        })

                    self.sendJSON(data)

            elif action == "remove_avatar":
                idavatar = message["idavatar"]
                iduser = message["iduser"]
                async with db.engine.acquire() as conn:
                    await conn.execute("DELETE FROM `avatars` "
                                              "WHERE `idUser` = %s "
                                              "AND `idAvatar` = %s", (iduser, idavatar))

            elif action == "add_avatar":
                who = message['user']
                avatar = message['avatar']

                async with db.engine.acquire() as conn:
                    if avatar is None:
                        await conn.execute(
                            "DELETE FROM `avatars` "
                            "WHERE `idUser` = "
                            "(SELECT `id` FROM `login` WHERE `login`.`login` = %s)", (who, ))
                    else:
                        await conn.execute(
                            "INSERT INTO `avatars`(`idUser`, `idAvatar`) "
                            "VALUES ((SELECT id FROM login WHERE login.login = %s),"
                            "(SELECT id FROM avatars_list WHERE avatars_list.url = %s)) "
                            "ON DUPLICATE KEY UPDATE `idAvatar` = (SELECT id FROM avatars_list WHERE avatars_list.url = %s)",
                            (who, avatar, avatar))

            elif action == "broadcast":
                for player in self.player_service:
                    try:
                        if player.lobby_connection:
                            player.lobby_connection.send_warning(message.get('message'))
                    except Exception as ex:
                        self._logger.debug("Could not send broadcast message to %s: %s".format(player, ex))

        elif self.player.mod:
            if action == "join_channel":
                user_ids = message['user_ids']
                channel = message['channel']

                for user_id in user_ids:
                    player = self.player_service[message[user_id]]
                    if player:
                        player.lobby_connection.sendJSON(dict(command="social", autojoin=[channel]))

    async def check_user_login(self, conn, login, password):
        # TODO: Hash passwords server-side so the hashing actually *does* something.
        result = await conn.execute(
            "SELECT login.id as id,"
            "login.login as username,"
            "login.password as password,"
            "login.steamid as steamid,"
            "login.create_time as create_time,"
            "lobby_ban.reason as reason,"
            "lobby_ban.expires_at as expires_at "
            "FROM login "
            "LEFT JOIN lobby_ban ON login.id = lobby_ban.idUser "
            "WHERE LOWER(login)=%s "
            "ORDER BY expires_at DESC", (login.lower(), ))

        auth_error_message = "Login not found or password incorrect. They are case sensitive."
        row = await result.fetchone()
        if not row:
            raise AuthenticationError(auth_error_message)

        player_id, real_username, dbPassword, steamid, create_time, ban_reason, ban_expiry = (row[i] for i in range(7))

        if dbPassword != password:
            raise AuthenticationError(auth_error_message)

        now = datetime.datetime.now()

        if ban_reason is not None and now < ban_expiry:
            self._logger.debug('Rejected login from banned user: %s, %s, %s', player_id, login, self.session)
            raise ClientError("You are banned from FAF for {}.\n Reason :\n {}".format(humanize.naturaldelta(ban_expiry-now), ban_reason), recoverable=False)

        # New accounts are prevented from playing if they didn't link to steam

        if config.FORCE_STEAM_LINK and not steamid and create_time.timestamp() > config.FORCE_STEAM_LINK_AFTER_DATE:
            self._logger.debug('Rejected login from new user: %s, %s, %s', player_id, login, self.session)
            raise ClientError(
                "Unfortunately, you must currently link your account to Steam in order to play Forged Alliance Forever. You can do so on <a href='{steamlink_url}'>{steamlink_url}</a>.".format(steamlink_url=config.WWW_URL + '/account/link'),
                recoverable=False)

        self._logger.debug("Login from: %s, %s, %s", player_id, login, self.session)

        return player_id, real_username, steamid

    def check_version(self, message):
        versionDB, updateFile = self.player_service.client_version_info
        update_msg = dict(command="update",
                          update=updateFile,
                          new_version=versionDB)

        self.user_agent = message.get('user_agent')
        version = message.get('version')
        server.stats.gauge('user.agents.None', -1, delta=True)
        server.stats.gauge('user.agents.{}'.format(self.user_agent), 1, delta=True)

        if not version or not self.user_agent:
            update_msg['command'] = 'welcome'
            # For compatibility with 0.10.x updating mechanism
            self.sendJSON(update_msg)
            return False

        # Check their client is reporting the right version number.
        if 'downlords-faf-client' not in self.user_agent:
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

    async def check_policy_conformity(self, player_id, uid_hash, session):
        url = FAF_POLICY_SERVER_BASE_URL + '/verify'
        payload = dict(player_id=player_id, uid_hash=uid_hash, session=session)
        headers = {
            'content-type': "application/json",
            'cache-control': "no-cache"
        }

        response = requests.post(url, json=payload, headers=headers).json()

        if response.get('result', '') == 'vm':
            self._logger.debug("Using VM: %d: %s", player_id, uid_hash)
            self.sendJSON(dict(command="notice", style="error",
                               text="You need to link your account to Steam in order to use FAF in a virtual machine. "
                                    "Please contact an admin or moderator on the forums if you feel this is a false positive."))
            self.send_warning("Your computer seems to be a virtual machine.<br><br>In order to "
                              "log in from a VM, you have to link your account to Steam: <a href='" +
                              config.WWW_URL + "/account/link'>" +
                              config.WWW_URL + "/account/link</a>.<br>If you need an exception, please contact an "
                                               "admin or moderator on the forums", fatal=True)

        if response.get('result', '') == 'already_associated':
            self._logger.warning("UID hit: %d: %s", player_id, uid_hash)
            self.send_warning("Your computer is already associated with another FAF account.<br><br>In order to "
                              "log in with an additional account, you have to link it to Steam: <a href='" +
                              config.WWW_URL + "/account/link'>" +
                              config.WWW_URL + "/account/link</a>.<br>If you need an exception, please contact an "
                                               "admin or moderator on the forums", fatal=True)
            return False

        if response.get('result', '') == 'fraudulent':
            self._logger.info("Banning player %s for fraudulent looking login.", player_id)
            self.send_warning("Fraudulent login attempt detected. As a precautionary measure, your account has been "
                              "banned permanently. Please contact an admin or moderator on the forums if you feel this is "
                              "a false positive.",
                              fatal=True)

            with await db.engine.acquire() as conn:
                try:
                    await conn.execute(
                        "INSERT INTO ban (player_id, author_id, reason, level) VALUES (%s, %s, %s, 'GLOBAL')",
                        (player_id, player_id, "Auto-banned because of fraudulent login attempt"))
                except pymysql.MySQLError as e:
                    raise ClientError('Banning failed: {}'.format(e))

            return False

        return response.get('result', '') == 'honest'

    async def command_hello(self, message):
        login = message['login'].strip()
        password = message['password']

        async with db.engine.acquire() as conn:
            player_id, login, steamid = await self.check_user_login(conn, login, password)
            server.stats.incr('user.logins')
            server.stats.gauge('users.online', len(self.player_service))

            await conn.execute(
                "UPDATE login SET ip = %(ip)s, user_agent = %(user_agent)s, last_login = NOW() WHERE id = %(player_id)s",
                {
                    "ip": self.peer_address.host,
                    "user_agent": self.user_agent,
                    "player_id": player_id
                })

            if not self.player_service.is_uniqueid_exempt(player_id) and steamid is None:
                conforms_policy = await self.check_policy_conformity(player_id, message['unique_id'], self.session)
                if not conforms_policy:
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
                await conn.execute("UPDATE anope.anope_db_NickCore SET pass = %s WHERE display = %s", (irc_pass, login))
            except (pymysql.OperationalError, pymysql.ProgrammingError):
                self._logger.error("Failure updating NickServ password for %s", login)

        permission_group = self.player_service.get_permission_group(player_id)
        self.player = Player(
            login=str(login),
            session=self.session,
            ip=self.peer_address.host,
            id=player_id,
            permissionGroup=permission_group,
            lobby_connection=self
        )

        old_player = self.player_service.get_player(self.player.id)
        if old_player:
            self._logger.debug("player {} already signed in: {}".format(self.player.id, old_player))
            if old_player.lobby_connection:
                old_player.lobby_connection.send_warning("You have been signed out because you signed in elsewhere.", fatal=True)
                old_player.lobby_connection.game_connection = None
                old_player.lobby_connection.player = None
                self._logger.debug("Removing previous game_connection and player reference of player {} in hope on_connection_lost() wouldn't drop her out of the game".format(self.player.id))

        await self.player_service.fetch_player_data(self.player)

        self.player_service[self.player.id] = self.player
        self._authenticated = True

        # Country
        # -------
        self.player.country = self.geoip_service.country(self.peer_address.host)

        # Send the player their own player info.
        self.sendJSON({
            "command": "welcome",
            "me": self.player.to_dict(),

            # For backwards compatibility for old clients. For now.
            "id": self.player.id,
            "login": login
        })

        # Tell player about everybody online. This must happen after "welcome".
        self.sendJSON(
            {
                "command": "player_info",
                "players": [player.to_dict() for player in self.player_service]
            }
        )

        # Tell everyone else online about us. This must happen after all the player_info messages.
        # This ensures that no other client will perform an operation that interacts with the
        # incoming user, allowing the client to make useful assumptions: it can be certain it has
        # initialised its local player service before it is going to get messages that want to
        # query it.
        self.player_service.mark_dirty(self.player)

        friends = []
        foes = []
        async with db.engine.acquire() as conn:
            result = await conn.execute(
                "SELECT `subject_id`, `status` "
                "FROM friends_and_foes WHERE user_id = %s", (self.player.id,))

            async for row in result:
                target_id, status = row["subject_id"], row["status"]
                if status == "FRIEND":
                    friends.append(target_id)
                else:
                    foes.append(target_id)

        self.player.friends = set(friends)
        self.player.foes = set(foes)

        channels = []
        if self.player.mod:
            channels.append("#moderators")

        if self.player.clan is not None:
            channels.append("#%s_clan" % self.player.clan)

        json_to_send = {"command": "social", "autojoin": channels, "channels": channels, "friends": friends, "foes": foes, "power": permission_group}
        self.sendJSON(json_to_send)

        self.send_mod_list()
        self.send_game_list()

    def command_restore_game_session(self, message):
        game_id = int(message.get('game_id'))

        # Restore the player's game connection, if the game still exists and is live
        if not game_id or game_id not in self.game_service:
            self.send_warning("The game you were connected to does no longer exist")
            return

        game = self.game_service[game_id]  # type: Game
        if game.state != GameState.LOBBY and game.state != GameState.LIVE:
            self.send_warning("The game you were connected to is no longer available")
            return

        self._logger.debug("Restoring game session of player %s to game %s", self.player, game)
        self.game_connection = GameConnection(
            game=game,
            player=self.player,
            protocol=self.protocol,
            player_service=self.player_service,
            games=self.game_service,
            state=GameConnectionState.CONNECTED_TO_HOST
        )

        game.add_game_connection(self.game_connection)
        self.player.state = PlayerState.PLAYING
        if not hasattr(self.player, "game"):
            self.player.game = game

    @timed
    def command_ask_session(self, message):
        if self.check_version(message):
            self.sendJSON({
                "command": "session",
                "session": self.session
            })

    async def command_avatar(self, message):
        action = message['action']

        if action == "list_avatar":
            avatarList = []

            async with db.engine.acquire() as conn:
                result = await conn.execute(
                    "SELECT url, tooltip FROM `avatars` "
                    "LEFT JOIN `avatars_list` ON `idAvatar` = `avatars_list`.`id` WHERE `idUser` = %s", (self.player.id,))

                async for row in result:
                    avatar = {"url": row["url"], "tooltip": row["tooltip"]}
                    avatarList.append(avatar)

                if len(avatarList) > 0:
                    self.sendJSON({"command": "avatar", "avatarlist": avatarList})

        elif action == "select":
            avatar = message['avatar']

            async with db.engine.acquire() as conn:
                await conn.execute(
                    "UPDATE `avatars` SET `selected` = 0 WHERE `idUser` = %s", (self.player.id, ))
                if avatar is not None:
                    await conn.execute(
                        "UPDATE `avatars` SET `selected` = 1 WHERE `idAvatar` ="
                        "(SELECT id FROM avatars_list WHERE avatars_list.url = %s) and "
                        "`idUser` = %s", (avatar, self.player.id))
        else:
            raise KeyError('invalid action')

    @timed
    def command_game_join(self, message):
        """
        We are going to join a game.
        """
        assert isinstance(self.player, Player)

        if self._attempted_connectivity_test:
            raise ClientError("Cannot join game. Please update your client to the newest version.")

        uuid = int(message['uid'])
        password = message.get('password', None)

        self._logger.debug("joining: %d with pw: %s", uuid, password)
        try:
            game = self.game_service[uuid]
            if not game or game.state != GameState.LOBBY:
                self._logger.debug("Game not in lobby state: %s", game)
                self.sendJSON(dict(command="notice", style="info", text="The game you are trying to join is not ready."))
                return

            if game.password != password:
                self.sendJSON(dict(command="notice", style="info", text="Bad password (it's case sensitive)"))
                return

            self.launch_game(game, is_host=False)

        except KeyError:
            self.sendJSON(dict(command="notice", style="info", text="The host has left the game"))

    async def command_game_matchmaking(self, message):
        mod = str(message.get('mod', 'ladder1v1'))
        state = str(message['state'])

        if self._attempted_connectivity_test:
            raise ClientError("Cannot host game. Please update your client to the newest version.")

        if state == "stop":
            self.ladder_service.cancel_search(self.player)
            return

        async with db.engine.acquire() as conn:
            result = await conn.execute("SELECT id FROM matchmaker_ban WHERE `userid` = %s", (self.player.id))
            row = await result.fetchone()
            if row:
                self.sendJSON(dict(command="notice", style="error",
                                   text="You are banned from the matchmaker. Contact an admin to have the reason."))
                return

        if state == "start":
            assert self.player is not None
            self.player.faction = str(message['faction'])

            if mod == "ladder1v1":
                search = Search([self.player])
            else:
                # TODO: Put player parties here
                search = Search([self.player])

            self.ladder_service.start_search(self.player, search, queue_name=mod)

    def command_coop_list(self, message):
        """ Request for coop map list"""
        asyncio.ensure_future(self.send_coop_maps())

    @timed()
    def command_game_host(self, message):
        assert isinstance(self.player, Player)

        if self._attempted_connectivity_test:
            raise ClientError("Cannot join game. Please update your client to the newest version.")

        visibility = VisibilityState.from_string(message.get('visibility'))
        if not isinstance(visibility, VisibilityState):
            # Protocol violation.
            self.abort("{} sent a nonsense visibility code: {}".format(self.player.login, message.get('visibility')))
            return

        title = html.escape(message.get('title') or f"{self.player.login}'s game")

        try:
            title.encode('ascii')
        except UnicodeEncodeError:
            self.sendJSON(dict(command="notice", style="error", text="Non-ascii characters in game name detected."))
            return

        mod = message.get('mod') or 'faf'
        mapname = message.get('mapname') or 'scmp_007'
        password = message.get('password')
        game_mode = mod.lower()

        game = self.game_service.create_game(
            visibility=visibility,
            game_mode=game_mode,
            host=self.player,
            name=title,
            mapname=mapname,
            password=password
        )
        self.launch_game(game, is_host=True)
        server.stats.incr('game.hosted')

    def launch_game(self, game, is_host=False, use_map=None):
        # TODO: Fix setting up a ridiculous amount of cyclic pointers here
        if self.game_connection:
            self.game_connection.abort("Player launched a new game")

        if is_host:
            game.host = self.player

        self.game_connection = GameConnection(
            game=game,
            player=self.player,
            protocol=self.protocol,
            player_service=self.player_service,
            games=self.game_service
        )

        self.player.state = PlayerState.HOSTING if is_host else PlayerState.JOINING
        self.player.game = game
        cmd = {
            "command": "game_launch",
            "mod": game.game_mode,
            "uid": game.id,
            "args": ["/numgames " + str(self.player.numGames)]
        }
        if use_map:
            cmd['mapname'] = use_map
        self.sendJSON(cmd)

    async def command_modvault(self, message):
        type = message["type"]

        async with db.engine.acquire() as conn:
            if type == "start":
                result = await conn.execute("SELECT uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon FROM table_mod ORDER BY likes DESC LIMIT 100")

                async for row in result:
                    uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon = (row[i] for i in range(12))
                    try:
                        link = urllib.parse.urljoin(config.CONTENT_URL, "faf/vault/" + filename)
                        thumbstr = ""
                        if icon != "":
                            thumbstr = urllib.parse.urljoin(config.CONTENT_URL, "faf/vault/mods_thumbs/" + urllib.parse.quote(icon))

                        out = dict(command="modvault_info", thumbnail=thumbstr, link=link, bugreports=[],
                                   comments=[], description=description, played=played, likes=likes,
                                   downloads=downloads, date=int(date.timestamp()), uid=uid, name=name, version=version, author=author,
                                   ui=ui)
                        self.sendJSON(out)
                    except:
                        self._logger.error("Error handling table_mod row (uid: {})".format(uid), exc_info=True)
                        pass

            elif type == "like":
                canLike = True
                uid = message['uid']
                result = await conn.execute("SELECT uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon, likers FROM `table_mod` WHERE uid = %s LIMIT 1", (uid,))

                row = await result.fetchone()
                uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon, likerList = (row[i] for i in range(13))
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
                    await conn.execute(
                        "UPDATE mod_stats s "
                        "JOIN mod_version v ON v.mod_id = s.mod_id "
                        "SET s.likes = s.likes + 1, likers=%s WHERE v.uid = %s",
                        json.dumps(likers), uid)
                    self.sendJSON(out)

            elif type == "download":
                uid = message["uid"]
                await conn.execute(
                    "UPDATE mod_stats s "
                    "JOIN mod_version v ON v.mod_id = s.mod_id "
                    "SET downloads=downloads+1 WHERE v.uid = %s", uid)
            else:
                raise ValueError('invalid type argument')

    @asyncio.coroutine
    async def command_ice_servers(self, message):
        if not self.player:
            return

        ttl = TWILIO_TTL
        ice_servers = self.coturn_generator.server_tokens(
            username=self.player.id,
            ttl=ttl
        )

        if self.nts_client:
            ice_servers = ice_servers + await self.nts_client.server_tokens(ttl=ttl)

        self.sendJSON({
            'command': 'ice_servers',
            'ice_servers': ice_servers,
            'ttl': ttl
        })

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
        self._logger.log(TRACE, ">>: %s", message)
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
            self._logger.debug(
                "Lost lobby connection killing game connection for player {}".format(self.game_connection.player.id))
            await self.game_connection.on_connection_lost()

        self.ladder_service.on_connection_lost(self.player)

        if self.player:
            self._logger.debug("Lost lobby connection removing player {}".format(self.player.id))
            self.player_service.remove_player(self.player)
