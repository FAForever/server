import asyncio
import hashlib
import html
import json
import random
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

import aiohttp
import humanize
import pymysql
import semver
import server
from server.db import FAFDatabase
from sqlalchemy import and_, func, select, text

from . import config
from .abc.base_game import GameConnectionState
from .async_functions import gather_without_exceptions
from .config import FAF_POLICY_SERVER_BASE_URL, TRACE, TWILIO_TTL
from .db.models import ban, friends_and_foes, lobby_ban
from .db.models import login as t_login
from .decorators import timed, with_logger
from .game_service import GameService
from .gameconnection import GameConnection
from .games import GameState, VisibilityState
from .geoip_service import GeoIpService
from .ice_servers.coturn import CoturnHMAC
from .ice_servers.nts import TwilioNTS
from .ladder_service import LadderService
from .matchmaker import Search
from .player_service import PlayerService
from .players import Player, PlayerState
from .protocol import QDataStreamProtocol
from .rating import RatingType
from .types import Address


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
    def __init__(
        self,
        database: FAFDatabase,
        games: GameService,
        players: PlayerService,
        nts_client: Optional[TwilioNTS],
        geoip: GeoIpService,
        ladder_service: LadderService
    ):
        self._db = database
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
        server.stats.incr('server.connections')

    async def abort(self, logspam=""):
        if self.player:
            self._logger.warning("Client %s dropped. %s" % (self.player.login, logspam))
        else:
            self._logger.warning("Aborting %s. %s" % (self.peer_address.host, logspam))
        if self.game_connection:
            await self.game_connection.abort()
            self.game_connection = None
        self._authenticated = False
        self.protocol.writer.close()

        if self.player:
            self.player_service.remove_player(self.player)
            self.player = None
        server.stats.incr('server.connections.aborted')

    async def ensure_authenticated(self, cmd):
        if not self._authenticated:
            if cmd not in ['hello', 'ask_session', 'create_account', 'ping', 'pong', 'Bottleneck']:  # Bottleneck is sent by the game during reconnect
                server.stats.incr('server.received_messages.unauthenticated', tags={"command": cmd})
                await self.abort("Message invalid for unauthenticated connection: %s" % cmd)
                return False
        return True

    async def on_message_received(self, message):
        """
        Dispatches incoming messages
        """
        self._logger.log(TRACE, "<<: %s", message)

        try:
            cmd = message['command']
            if not await self.ensure_authenticated(cmd):
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

            handler = getattr(self, 'command_{}'.format(cmd))
            await handler(message)

        except AuthenticationError as ex:
            await self.send({
                'command': 'authentication_failed',
                'text': ex.message
            })
        except ClientError as ex:
            self._logger.warning("Client error: %s", ex.message)
            await self.send({
                'command': 'notice',
                'style': 'error',
                'text': ex.message
            })
            if not ex.recoverable:
                await self.abort(ex.message)
        except (KeyError, ValueError) as ex:
            self._logger.exception(ex)
            await self.abort("Garbage command: {}".format(message))
        except ConnectionError as e:
            # Propagate connection errors to the ServerContext error handler.
            raise e
        except Exception as ex:  # pragma: no cover
            await self.send({'command': 'invalid'})
            self._logger.exception(ex)
            await self.abort("Error processing command")

    async def command_ping(self, msg):
        await self.protocol.send_raw(self.protocol.pack_message('PONG'))

    async def command_pong(self, msg):
        pass

    async def command_create_account(self, message):
        raise ClientError("FAF no longer supports direct registration. Please use the website to register.", recoverable=True)

    async def command_coop_list(self, message):
        """ Request for coop map list"""
        async with self._db.acquire() as conn:
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

        await self.protocol.send_messages(maps)

    async def command_matchmaker_info(self, message):
        await self.send({
            'command': 'matchmaker_info',
            'queues': [queue.to_dict() for queue in self.ladder_service.queues.values()]
        })

    async def send_game_list(self):
        await self.send({
            'command': 'game_info',
            'games': [game.to_dict() for game in self.game_service.open_games]
        })

    async def command_social_remove(self, message):
        if "friend" in message:
            subject_id = message["friend"]
        elif "foe" in message:
            subject_id = message["foe"]
        else:
            await self.abort("No-op social_remove.")
            return

        async with self._db.acquire() as conn:
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

        async with self._db.acquire() as conn:
            await conn.execute(friends_and_foes.insert().values(
                user_id=self.player.id,
                status=status,
                subject_id=subject_id,
            ))

    async def kick(self):
        await self.send({
            "command": "notice",
            "style": "kick",
        })
        await self.abort()

    async def send_updated_achievements(self, updated_achievements):
        await self.send({
            "command": "updated_achievements",
            "updated_achievements": updated_achievements
        })

    async def command_admin(self, message):
        action = message['action']

        if self.player.admin:
            if action == "closeFA":
                player = self.player_service[message['user_id']]
                if player:
                    self._logger.warning('Administrative action: %s closed game for %s', self.player, player)
                    await player.lobby_connection.send({
                        "command": "notice",
                        "style": "kill",
                    })

            elif action == "closelobby":
                player = self.player_service[message['user_id']]
                ban_fail = None
                if player:
                    if 'ban' in message:
                        reason = message['ban'].get('reason', 'Unspecified')
                        duration = int(message['ban'].get('duration', 1))
                        period = message['ban'].get('period', 'SECOND').upper()

                        self._logger.warning('Administrative action: %s closed client for %s with %s ban (Reason: %s)', self.player, player, duration, reason)
                        async with self._db.acquire() as conn:
                            try:
                                result = await conn.execute("SELECT reason from lobby_ban WHERE idUser=%s AND expires_at > NOW()", (message['user_id']))

                                row = await result.fetchone()
                                if row:
                                    ban_fail = row[0]
                                else:
                                    if period not in ["SECOND", "DAY", "WEEK", "MONTH"]:
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
                    await player.lobby_connection.kick()
                    if ban_fail:
                        raise ClientError("Kicked the player, but he was already banned!")

            elif action == "broadcast":
                message_text = message.get('message')
                if not message_text:
                    return

                tasks = []
                for player in self.player_service:
                    # Check if object still exists:
                    # https://docs.python.org/3/library/weakref.html#weak-reference-objects
                    if player.lobby_connection is not None:
                        tasks.append(
                            player.lobby_connection.send_warning(message_text)
                        )

                await gather_without_exceptions(tasks, ConnectionError)

        if self.player.mod:
            if action == "join_channel":
                user_ids = message['user_ids']
                channel = message['channel']

                tasks = []
                for user_id in user_ids:
                    player = self.player_service[user_id]
                    if player and player.lobby_connection is not None:
                        tasks.append(player.lobby_connection.send({
                            "command": "social",
                            "autojoin": [channel]
                        }))

                await gather_without_exceptions(tasks, ConnectionError)

    async def check_user_login(self, conn, username, password):
        # TODO: Hash passwords server-side so the hashing actually *does* something.
        result = await conn.execute(
            select([
                t_login.c.id,
                t_login.c.login,
                t_login.c.password,
                t_login.c.steamid,
                t_login.c.create_time,
                lobby_ban.c.reason,
                lobby_ban.c.expires_at
            ]).select_from(t_login.outerjoin(lobby_ban))
            .where(t_login.c.login == username)
            .order_by(lobby_ban.c.expires_at.desc())
        )

        auth_error_message = "Login not found or password incorrect. They are case sensitive."
        row = await result.fetchone()
        if not row:
            server.stats.incr('user.logins', tags={'status': 'failure'})
            raise AuthenticationError(auth_error_message)

        player_id = row[t_login.c.id]
        real_username = row[t_login.c.login]
        dbPassword = row[t_login.c.password]
        steamid = row[t_login.c.steamid]
        create_time = row[t_login.c.create_time]
        ban_reason = row[lobby_ban.c.reason]
        ban_expiry = row[lobby_ban.c.expires_at]

        if dbPassword != password:
            server.stats.incr('user.logins', tags={'status': 'failure'})
            raise AuthenticationError(auth_error_message)

        now = datetime.now()
        if ban_reason is not None and now < ban_expiry:
            self._logger.debug('Rejected login from banned user: %s, %s, %s',
                               player_id, username, self.session)

            await self.send_ban_message_and_abort(ban_expiry - now, ban_reason)

        # New accounts are prevented from playing if they didn't link to steam

        if config.FORCE_STEAM_LINK and not steamid and create_time.timestamp() > config.FORCE_STEAM_LINK_AFTER_DATE:
            self._logger.debug('Rejected login from new user: %s, %s, %s', player_id, username, self.session)
            raise ClientError(
                "Unfortunately, you must currently link your account to Steam in order to play Forged Alliance Forever. You can do so on <a href='{steamlink_url}'>{steamlink_url}</a>.".format(steamlink_url=config.WWW_URL + '/account/link'),
                recoverable=False)

        self._logger.debug("Login from: %s, %s, %s", player_id, username, self.session)

        return player_id, real_username, steamid

    async def check_version(self, message):
        versionDB, updateFile = self.player_service.client_version_info
        update_msg = {
            'command': 'update',
            'update': updateFile,
            'new_version': versionDB
        }

        self.user_agent = message.get('user_agent')
        version = message.get('version')
        server.stats.gauge('user.agents.None', -1, delta=True)
        server.stats.gauge('user.agents.{}'.format(self.user_agent), 1, delta=True)

        if not self.user_agent or 'downlords-faf-client' not in self.user_agent:
            await self.send_warning(
                "You are using an unofficial client version! "
                "Some features might not work as expected. "
                "If you experience any problems please download the latest "
                "version of the official client from "
                f'<a href="{config.WWW_URL}">{config.WWW_URL}</a>'
            )

        if not version or not self.user_agent:
            update_msg['command'] = 'welcome'
            # For compatibility with 0.10.x updating mechanism
            await self.send(update_msg)
            return False

        # Check their client is reporting the right version number.
        if 'downlords-faf-client' not in self.user_agent:
            try:
                if "-" in version:
                    version = version.split('-')[0]
                if "+" in version:
                    version = version.split('+')[0]
                if semver.compare(versionDB, version) > 0:
                    await self.send(update_msg)
                    return False
            except ValueError:
                await self.send(update_msg)
                return False
        return True

    async def check_policy_conformity(self, player_id, uid_hash, session, ignore_result=False):
        url = FAF_POLICY_SERVER_BASE_URL + '/verify'
        payload = {
            "player_id": player_id,
            "uid_hash": uid_hash,
            "session": session
        }
        headers = {
            'content-type': "application/json",
            'cache-control': "no-cache"
        }

        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                response = await resp.json()

        if ignore_result:
            return True

        if response.get('result', '') == 'vm':
            self._logger.debug("Using VM: %d: %s", player_id, uid_hash)
            await self.send({
                "command": "notice",
                "style": "error",
                "text": (
                    "You need to link your account to Steam in order to use "
                    "FAF in a virtual machine. Please contact an admin or "
                    "moderator on the forums if you feel this is a false "
                    "positive."
                )
            })
            await self.send_warning("Your computer seems to be a virtual machine.<br><br>In order to "
                              "log in from a VM, you have to link your account to Steam: <a href='" +
                              config.WWW_URL + "/account/link'>" +
                              config.WWW_URL + "/account/link</a>.<br>If you need an exception, please contact an "
                                               "admin or moderator on the forums", fatal=True)

        if response.get('result', '') == 'already_associated':
            self._logger.warning("UID hit: %d: %s", player_id, uid_hash)
            await self.send_warning("Your computer is already associated with another FAF account.<br><br>In order to "
                              "log in with an additional account, you have to link it to Steam: <a href='" +
                              config.WWW_URL + "/account/link'>" +
                              config.WWW_URL + "/account/link</a>.<br>If you need an exception, please contact an "
                                               "admin or moderator on the forums", fatal=True)
            return False

        if response.get('result', '') == 'fraudulent':
            self._logger.info("Banning player %s for fraudulent looking login.", player_id)
            await self.send_warning("Fraudulent login attempt detected. As a precautionary measure, your account has been "
                              "banned permanently. Please contact an admin or moderator on the forums if you feel this is "
                              "a false positive.",
                              fatal=True)

            async with self._db.acquire() as conn:
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

        async with self._db.acquire() as conn:
            player_id, login, steamid = await self.check_user_login(conn, login, password)
            server.stats.incr('user.logins', tags={'status': 'success'})
            server.stats.gauge('users.online', len(self.player_service))

            await conn.execute(
                "UPDATE login SET ip = %(ip)s, user_agent = %(user_agent)s, last_login = NOW() WHERE id = %(player_id)s",
                {
                    "ip": self.peer_address.host,
                    "user_agent": self.user_agent,
                    "player_id": player_id
                })

            conforms_policy = await self.check_policy_conformity(
                player_id, message['unique_id'], self.session,
                ignore_result=(
                    steamid is not None or
                    self.player_service.is_uniqueid_exempt(player_id)
                )
            )
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
            player_id=player_id,
            permission_group=permission_group,
            lobby_connection=self
        )

        old_player = self.player_service.get_player(self.player.id)
        if old_player:
            self._logger.debug("player {} already signed in: {}".format(self.player.id, old_player))
            if old_player.lobby_connection:
                await old_player.lobby_connection.send_warning("You have been signed out because you signed in elsewhere.", fatal=True)
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
        await self.send({
            "command": "welcome",
            "me": self.player.to_dict(),

            # For backwards compatibility for old clients. For now.
            "id": self.player.id,
            "login": login
        })

        # Tell player about everybody online. This must happen after "welcome".
        await self.send({
            "command": "player_info",
            "players": [player.to_dict() for player in self.player_service]
        })

        # Tell everyone else online about us. This must happen after all the player_info messages.
        # This ensures that no other client will perform an operation that interacts with the
        # incoming user, allowing the client to make useful assumptions: it can be certain it has
        # initialised its local player service before it is going to get messages that want to
        # query it.
        self.player_service.mark_dirty(self.player)

        friends = []
        foes = []
        async with self._db.acquire() as conn:
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
        await self.send(json_to_send)

        await self.send_game_list()

    async def command_restore_game_session(self, message):
        game_id = int(message.get('game_id'))

        # Restore the player's game connection, if the game still exists and is live
        if not game_id or game_id not in self.game_service:
            await self.send_warning("The game you were connected to does no longer exist")
            return

        game = self.game_service[game_id]  # type: Game
        if game.state != GameState.LOBBY and game.state != GameState.LIVE:
            await self.send_warning("The game you were connected to is no longer available")
            return

        self._logger.debug("Restoring game session of player %s to game %s", self.player, game)
        self.game_connection = GameConnection(
            database=self._db,
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

    async def command_ask_session(self, message):
        if await self.check_version(message):
            await self.send({"command": "session", "session": self.session})

    async def command_avatar(self, message):
        action = message['action']

        if action == "list_avatar":
            avatarList = []

            async with self._db.acquire() as conn:
                result = await conn.execute(
                    "SELECT url, tooltip FROM `avatars` "
                    "LEFT JOIN `avatars_list` ON `idAvatar` = `avatars_list`.`id` WHERE `idUser` = %s", (self.player.id,))

                async for row in result:
                    avatar = {"url": row["url"], "tooltip": row["tooltip"]}
                    avatarList.append(avatar)

                if avatarList:
                    await self.send({"command": "avatar", "avatarlist": avatarList})

        elif action == "select":
            avatar = message['avatar']

            async with self._db.acquire() as conn:
                await conn.execute(
                    "UPDATE `avatars` SET `selected` = 0 WHERE `idUser` = %s", (self.player.id, ))
                if avatar is not None:
                    await conn.execute(
                        "UPDATE `avatars` SET `selected` = 1 WHERE `idAvatar` ="
                        "(SELECT id FROM avatars_list WHERE avatars_list.url = %s) and "
                        "`idUser` = %s", (avatar, self.player.id))
        else:
            raise KeyError('invalid action')

    async def command_game_join(self, message):
        """
        We are going to join a game.
        """
        assert isinstance(self.player, Player)

        if self._attempted_connectivity_test:
            raise ClientError("Cannot join game. Please update your client to the newest version.")

        await self.abort_connection_if_banned()

        uuid = int(message['uid'])
        password = message.get('password', None)

        self._logger.debug("joining: %d with pw: %s", uuid, password)
        try:
            game = self.game_service[uuid]
            if not game or game.state != GameState.LOBBY:
                self._logger.debug("Game not in lobby state: %s", game)
                await self.send({
                    "command": "notice",
                    "style": "info",
                    "text": "The game you are trying to join is not ready."
                })
                return

            if game.password != password:
                await self.send({
                    "command": "notice",
                    "style": "info",
                    "text": "Bad password (it's case sensitive)"
                })
                return

            await self.launch_game(game, is_host=False)

        except KeyError:
            await self.send({
                "command": "notice",
                "style": "info",
                "text": "The host has left the game"
            })

    async def command_game_matchmaking(self, message):
        mod = str(message.get('mod', 'ladder1v1'))
        state = str(message['state'])

        if self._attempted_connectivity_test:
            raise ClientError("Cannot host game. Please update your client to the newest version.")

        if state == "stop":
            self.ladder_service.cancel_search(self.player)
            return

        if state == "start":
            assert self.player is not None
            # Faction can be either the name (e.g. 'uef') or the enum value (e.g. 1)
            self.player.faction = message['faction']

            if mod == "ladder1v1":
                search = Search([self.player])
            else:
                # TODO: Put player parties here
                search = Search([self.player])

            await self.ladder_service.start_search(self.player, search, queue_name=mod)

    async def command_game_host(self, message):
        assert isinstance(self.player, Player)

        if self._attempted_connectivity_test:
            raise ClientError("Cannot join game. Please update your client to the newest version.")

        await self.abort_connection_if_banned()

        visibility = VisibilityState.from_string(message.get('visibility'))
        if not isinstance(visibility, VisibilityState):
            # Protocol violation.
            await self.abort("{} sent a nonsense visibility code: {}".format(self.player.login, message.get('visibility')))
            return

        title = html.escape(message.get('title') or f"{self.player.login}'s game")

        try:
            title.encode('ascii')
        except UnicodeEncodeError:
            await self.send({
                "command": "notice",
                "style": "error",
                "text": "Non-ascii characters in game name detected."
            })
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
        await self.launch_game(game, is_host=True)
        server.stats.incr('game.hosted', tags={'game_mode': game_mode})

    async def launch_game(self, game, is_host=False, use_map=None):
        # TODO: Fix setting up a ridiculous amount of cyclic pointers here
        if self.game_connection:
            await self.game_connection.abort("Player launched a new game")

        if is_host:
            game.host = self.player

        self.game_connection = GameConnection(
            database=self._db,
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
            "args": ["/numgames", self.player.game_count[RatingType.GLOBAL]],
            "uid": game.id,
            "mod": game.game_mode,
            "mapname": use_map,
            # Following parameters are not used by the client yet. They are
            # needed for setting up auto-lobby style matches such as ladder, gw,
            # and team machmaking where the server decides what these game
            # options are. Currently, options for ladder are hardcoded into the
            # client.
            "name": game.name,
            "team": game.get_player_option(self.player, "Team"),
            "faction": game.get_player_option(self.player, "Faction"),
            "expected_players": len(game.players) or None,
            "map_position": game.get_player_option(self.player, "StartSpot"),
            "init_mode": game.init_mode.value,
        }

        # Remove args with None value
        await self.send({k: v for k, v in cmd.items() if v is not None})

    async def command_modvault(self, message):
        type = message["type"]

        async with self._db.acquire() as conn:
            if type == "start":
                result = await conn.execute("SELECT uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon FROM table_mod ORDER BY likes DESC LIMIT 100")

                async for row in result:
                    uid, name, version, author, ui, date, downloads, likes, played, description, filename, icon = (row[i] for i in range(12))
                    try:
                        link = urllib.parse.urljoin(config.CONTENT_URL, "faf/vault/" + filename)
                        thumbstr = ""
                        if icon:
                            thumbstr = urllib.parse.urljoin(config.CONTENT_URL, "faf/vault/mods_thumbs/" + urllib.parse.quote(icon))

                        out = dict(command="modvault_info", thumbnail=thumbstr, link=link, bugreports=[],
                                   comments=[], description=description, played=played, likes=likes,
                                   downloads=downloads, date=int(date.timestamp()), uid=uid, name=name, version=version, author=author,
                                   ui=ui)
                        await self.send(out)
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
                if icon:
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
                    await self.send(out)

            elif type == "download":
                uid = message["uid"]
                await conn.execute(
                    "UPDATE mod_stats s "
                    "JOIN mod_version v ON v.mod_id = s.mod_id "
                    "SET downloads=downloads+1 WHERE v.uid = %s", uid)
            else:
                raise ValueError('invalid type argument')

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

        await self.send({
            'command': 'ice_servers',
            'ice_servers': ice_servers,
            'ttl': ttl
        })

    async def send_warning(self, message: str, fatal: bool=False):
        """
        Display a warning message to the client
        :param message: Warning message to display
        :param fatal: Whether or not the warning is fatal.
                      If the client receives a fatal warning it should disconnect
                      and not attempt to reconnect.
        :return: None
        """
        await self.send({
            'command': 'notice',
            'style': 'info' if not fatal else 'error',
            'text': message
        })
        if fatal:
            await self.abort(message)

    async def send(self, message):
        """

        :param message:
        :return:
        """
        self._logger.log(TRACE, ">>: %s", message)
        await self.protocol.send_message(message)

    async def drain(self):
        # TODO: Remove me, QDataStreamProtocol no longer has a drain method
        pass

    async def on_connection_lost(self):
        async def nop(*args, **kwargs):
            return
        self.drain = nop
        self.send = nop
        if self.game_connection:
            self._logger.debug(
                "Lost lobby connection killing game connection for player {}".format(self.game_connection.player.id))
            await self.game_connection.on_connection_lost()

        self.ladder_service.on_connection_lost(self.player)

        if self.player:
            self._logger.debug("Lost lobby connection removing player {}".format(self.player.id))
            self.player_service.remove_player(self.player)

    async def abort_connection_if_banned(self):
        async with self._db.acquire() as conn:
            now = datetime.now()
            result = await conn.execute(
                select([lobby_ban.c.reason, lobby_ban.c.expires_at])
                .where(lobby_ban.c.idUser == self.player.id)
                .order_by(lobby_ban.c.expires_at.desc())
            )

            data = await result.fetchone()
            if data is None:
                return

            ban_expiry = data[ban.c.expires_at]

            if now < ban_expiry:
                self._logger.debug('Aborting connection of banned user: %s, %s, %s',
                                   self.player.id, self.player.login, self.session)
                self.send_ban_message_and_abort(ban_expiry - now, data[ban.c.reason])

    def send_ban_message_and_abort(self, ban_time, reason):
        ban_time_text = (f"for {humanize.naturaldelta(ban_time)}"
                         if ban_time.days < 365 * 100 else "forever")
        raise ClientError((f"You are banned from FAF {ban_time_text}.\n "
                           f"Reason :\n "
                           f"{reason}"), recoverable=False)
