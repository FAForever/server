import contextlib
import hashlib
import json
import random
import urllib.parse
import urllib.request
from datetime import datetime
from functools import wraps
from typing import Optional

import aiohttp
import humanize
import pymysql
import semver
from sqlalchemy import and_, func, select

import server.metrics as metrics
from server.db import FAFDatabase

from .abc.base_game import GameConnectionState, InitMode
from .config import TRACE, config
from .core import Protocol, RouteError
from .core import asyncio_extensions as asyncio_
from .core.connection import Connection, handler
from .core.typedefs import Address, Handler, HandlerDecorator
from .db.models import (
    avatars,
    avatars_list,
    ban,
    coop_map,
    friends_and_foes,
    lobby_ban
)
from .db.models import login as t_login
from .decorators import timed, with_logger
from .game_service import GameService
from .gameconnection import GameConnection
from .games import FeaturedModType, GameState, VisibilityState
from .geoip_service import GeoIpService
from .ice_servers.coturn import CoturnHMAC
from .ice_servers.nts import TwilioNTS
from .ladder_service import LadderService
from .player_service import PlayerService
from .players import Player, PlayerState
from .protocol import DisconnectedError
from .rating import InclusiveRange, RatingType
from .types import GameLaunchOptions


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


class BanError(Exception):
    def __init__(self, ban_expiry, ban_reason, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ban_expiry = ban_expiry
        self.ban_reason = ban_reason

    def message(self):
        return (f"You are banned from FAF {self._ban_duration_text()}. <br>"
                f"Reason : <br>"
                f"{self.ban_reason}")

    def _ban_duration_text(self):
        ban_duration = self.ban_expiry - datetime.utcnow()
        if ban_duration.days > 365 * 100:
            return "forever"
        humanized_ban_duration = humanize.precisedelta(
            ban_duration,
            minimum_unit="hours"
        )
        return f"for {humanized_ban_duration}"


class AuthenticationError(Exception):
    def __init__(self, message, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message


def public(func: Handler) -> Handler:
    """
    Mark a handler function as being callable without having logged in yet.
    """
    func.public = True
    return func


def permission(role: str) -> HandlerDecorator:
    """
    Ensure that a handler is only called if the player has the appropriate
    permission role.
    """
    def decorator(func: Handler) -> Handler:
        @wraps(func)
        async def wrapper(self, message):
            if (
                not self.player
                or not await self.player_service.has_permission_role(
                    self.player,
                    role
                )
            ):
                await self.send({"command": "permission_denied"})
                return

            await func(self, message)

        return wrapper
    return decorator


@with_logger
class LobbyConnection(Connection):
    @timed()
    def __init__(
        self,
        protocol: Protocol,
        address: Address,
        database: FAFDatabase,
        game_service: GameService,
        players: PlayerService,
        nts_client: Optional[TwilioNTS],
        geoip: GeoIpService,
        ladder_service: LadderService
    ):
        super().__init__(protocol, address)
        self._db = database
        self.geoip_service = geoip
        self.game_service = game_service
        self.player_service = players
        self.nts_client = nts_client
        self.coturn_generator = CoturnHMAC(
            config.COTURN_HOSTS,
            config.COTURN_KEYS
        )
        self.ladder_service = ladder_service
        self.authenticated = False
        self.player: Optional[Player] = None
        self.game_connection: Optional[GameConnection] = None
        self.session = int(random.randrange(0, 4294967295))
        self.user_agent = None
        self._version = None

        self._attempted_connectivity_test = False

        metrics.server_connections.inc()
        self._logger.debug("LobbyConnection initialized")

    def get_user_identifier(self) -> str:
        """For logging purposes"""
        if self.player:
            return self.player.login

        return str(self.session)

    async def abort(self, logspam=""):
        self.authenticated = False
        if self.player:
            self._logger.warning(
                "Client %s dropped. %s", self.player.login, logspam
            )
            self.player_service.remove_player(self.player)
            self.player = None
        else:
            self._logger.warning(
                "Aborting %s. %s", self.address.host, logspam
            )
        if self.game_connection:
            await self.game_connection.abort()

        await self.protocol.close()

    async def on_message_received(self, message):
        """
        Dispatches incoming messages
        """
        self._logger.log(TRACE, "<< %s: %s", self.get_user_identifier(), message)

        try:
            handler_func = self.dispatch(message)
            if not hasattr(handler_func, "public") and not self.authenticated:
                cmd = message["command"]
                metrics.unauth_messages.labels(cmd).inc()
                await self.abort(
                    f"Message invalid for unauthenticated connection: {cmd}"
                )
                return

            await handler_func(message)
        except AuthenticationError as ex:
            await self.send({
                "command": "authentication_failed",
                "text": ex.message
            })
        except BanError as ex:
            await self.send({
                "command": "notice",
                "style": "error",
                "text": ex.message()
            })
            await self.abort(ex.message())
        except ClientError as ex:
            self._logger.warning("Client error: %s", ex.message)
            await self.send({
                "command": "notice",
                "style": "error",
                "text": ex.message
            })
            if not ex.recoverable:
                await self.abort(ex.message)
        except (KeyError, ValueError) as ex:
            self._logger.exception(ex)
            await self.abort(f"Garbage command: {message}")
        except ConnectionError as e:
            # Propagate connection errors to the ServerContext error handler.
            raise e
        except Exception as ex:  # pragma: no cover
            if not isinstance(ex, RouteError):
                self._logger.exception(ex)
            await self.send({"command": "invalid"})
            await self.abort(f"Error processing message: {message}")

    async def _handle_game_message(self, message):
        if not self.game_connection:
            return

        await self.game_connection.on_message_received(message)

    @handler(target="game")
    async def target_game(self, message):
        await self._handle_game_message(message)

    @handler(target="game", command="Bottleneck")
    @public
    async def target_game_bottleneck(self, message):
        await self._handle_game_message(message)

    @handler(target="connectivity", command="InitiateTest")
    async def handle_initiate_test(self, message):
        self._attempted_connectivity_test = True
        raise ClientError(
            "Your client version is no longer supported. Please update to the "
            "newest version: https://faforever.com"
        )

    @handler("ping")
    @public
    async def command_ping(self, message):
        await self.send({"command": "pong"})

    @handler("pong")
    @public
    async def command_pong(self, message):
        pass

    @handler("create_account")
    @public
    async def command_create_account(self, message):
        raise ClientError(
            "FAF no longer supports direct registration. Please use the "
            "website to register.",
            recoverable=True
        )

    @handler("coop_list")
    async def command_coop_list(self, message):
        """Request for coop map list"""
        async with self._db.acquire() as conn:
            result = await conn.execute(select([coop_map]))

            maps = []
            campaigns = [
                "FA Campaign",
                "Aeon Vanilla Campaign",
                "Cybran Vanilla Campaign",
                "UEF Vanilla Campaign",
                "Custom Missions"
            ]
            async for row in result:
                json_to_send = {
                    "command": "coop_info",
                    "name": row["name"],
                    "description": row["description"],
                    "filename": row["filename"],
                    "featured_mod": "coop"
                }
                if row["type"] < len(campaigns):
                    json_to_send["type"] = campaigns[row["type"]]
                else:
                    # Don't sent corrupt data to the client...
                    self._logger.error("Unknown coop type!")
                    continue
                json_to_send["uid"] = row["id"]
                maps.append(json_to_send)

        await self.protocol.send_messages(maps)

    @handler("matchmaker_info")
    async def command_matchmaker_info(self, message):
        await self.send({
            "command": "matchmaker_info",
            "queues": [queue.to_dict() for queue in self.ladder_service.queues.values()]
        })

    @handler("social_remove")
    async def command_social_remove(self, message):
        if "friend" in message:
            subject_id = message["friend"]
            player_attr = self.player.friends
        elif "foe" in message:
            subject_id = message["foe"]
            player_attr = self.player.foes
        else:
            await self.abort("No-op social_remove.")
            return

        async with self._db.acquire() as conn:
            await conn.execute(friends_and_foes.delete().where(and_(
                friends_and_foes.c.user_id == self.player.id,
                friends_and_foes.c.subject_id == subject_id
            )))

        with contextlib.suppress(KeyError):
            player_attr.remove(subject_id)

    @handler("social_add")
    async def command_social_add(self, message):
        if "friend" in message:
            status = "FRIEND"
            subject_id = message["friend"]
            player_attr = self.player.friends
        elif "foe" in message:
            status = "FOE"
            subject_id = message["foe"]
            player_attr = self.player.foes
        else:
            return

        async with self._db.acquire() as conn:
            await conn.execute(friends_and_foes.insert().values(
                user_id=self.player.id,
                status=status,
                subject_id=subject_id,
            ))

        player_attr.add(subject_id)

    @handler("admin", action="closeFA")
    @permission("ADMIN_KICK_SERVER")
    async def command_admin_closefa(self, message):
        """Tell a client to kill ForgedAlliance.exe"""
        player = self.player_service[message["user_id"]]
        if player:
            self._logger.info(
                "Administrative action: %s closed game for %s",
                self.player, player
            )
            player.write_message({
                "command": "notice",
                "style": "kill",
            })

    @handler("admin", action="closelobby")
    @permission("ADMIN_KICK_SERVER")
    async def command_admin_closelobby(self, message):
        """Tell a client to close entirely"""
        player = self.player_service[message["user_id"]]
        if player and player.lobby_connection is not None:
            self._logger.info(
                "Administrative action: %s closed client for %s",
                self.player, player
            )
            with contextlib.suppress(DisconnectedError):
                await player.lobby_connection.kick()

    @handler("admin", action="broadcast")
    @permission("ADMIN_BROADCAST_MESSAGE")
    async def command_admin_broadcast(self, message):
        """Send a notice message to all online players"""
        message_text = message.get("message")
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

        self._logger.info(
            "%s broadcasting message to all players: %s",
            self.player.login, message_text
        )
        await asyncio_.gather_without_exceptions(tasks, Exception)

    @handler("admin", action="join_channel")
    @permission("ADMIN_JOIN_CHANNEL")
    async def command_admin_join_channel(self, message):
        """Tell a client to join an IRC channel"""
        user_ids = message["user_ids"]
        channel = message["channel"]

        for user_id in user_ids:
            player = self.player_service[user_id]
            if player:
                player.write_message({
                    "command": "social",
                    "autojoin": [channel]
                })

    @handler("admin")
    async def command_admin_other(self, message):
        """Ignore any other actions"""
        pass

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
            metrics.user_logins.labels("failure").inc()
            raise AuthenticationError(auth_error_message)

        player_id = row[t_login.c.id]
        real_username = row[t_login.c.login]
        dbPassword = row[t_login.c.password]
        steamid = row[t_login.c.steamid]
        create_time = row[t_login.c.create_time]
        ban_reason = row[lobby_ban.c.reason]
        ban_expiry = row[lobby_ban.c.expires_at]

        if dbPassword != password:
            metrics.user_logins.labels("failure").inc()
            raise AuthenticationError(auth_error_message)

        now = datetime.utcnow()
        if ban_reason is not None and now < ban_expiry:
            self._logger.debug("Rejected login from banned user: %s, %s, %s",
                               player_id, username, self.session)
            raise BanError(ban_expiry, ban_reason)

        # New accounts are prevented from playing if they didn't link to steam

        if config.FORCE_STEAM_LINK and not steamid and create_time.timestamp() > config.FORCE_STEAM_LINK_AFTER_DATE:
            self._logger.debug("Rejected login from new user: %s, %s, %s", player_id, username, self.session)
            raise ClientError(
                'Unfortunately, you must currently link your account to Steam in order to play Forged Alliance Forever. You can do so on <a href="{steamlink_url}">{steamlink_url}</a>.'.format(steamlink_url=config.WWW_URL + "/account/link"),
                recoverable=False)

        self._logger.debug("Login from: %s, %s, %s", player_id, username, self.session)

        return player_id, real_username, steamid

    def _set_user_agent_and_version(self, user_agent, version):
        metrics.user_connections.labels(str(self.user_agent)).dec()
        self.user_agent = user_agent
        metrics.user_connections.labels(str(self.user_agent)).inc()

        # only count a new version if it previously wasn't set
        # to avoid double counting
        if self._version is None and version is not None:
            metrics.user_agent_version.labels(str(version)).inc()
        self._version = version

    async def _check_version(self):
        versionDB, updateFile = self.player_service.client_version_info
        update_msg = {
            "command": "update",
            "update": updateFile,
            "new_version": versionDB
        }

        if not self.user_agent or "downlords-faf-client" not in self.user_agent:
            await self.send_warning(
                "You are using an unofficial client version! "
                "Some features might not work as expected. "
                "If you experience any problems please download the latest "
                "version of the official client from "
                f'<a href="{config.WWW_URL}">{config.WWW_URL}</a>'
            )

        if not self._version or not self.user_agent:
            update_msg["command"] = "welcome"
            # For compatibility with 0.10.x updating mechanism
            await self.send(update_msg)
            return False

        # Check their client is reporting the right version number.
        if "downlords-faf-client" not in self.user_agent:
            try:
                version = self._version
                if "-" in version:
                    version = version.split("-")[0]
                if "+" in version:
                    version = version.split("+")[0]
                if semver.compare(versionDB, version) > 0:
                    await self.send(update_msg)
                    return False
            except ValueError:
                await self.send(update_msg)
                return False
        return True

    async def check_policy_conformity(self, player_id, uid_hash, session, ignore_result=False):
        if not config.USE_POLICY_SERVER:
            return True

        url = config.FAF_POLICY_SERVER_BASE_URL + "/verify"
        payload = {
            "player_id": player_id,
            "uid_hash": uid_hash,
            "session": session
        }
        headers = {
            "content-type": "application/json",
            "cache-control": "no-cache"
        }

        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                response = await resp.json()

        if ignore_result:
            return True

        if response.get("result", "") == "vm":
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

        if response.get("result", "") == "already_associated":
            self._logger.warning("UID hit: %d: %s", player_id, uid_hash)
            await self.send_warning("Your computer is already associated with another FAF account.<br><br>In order to "
                                    "log in with an additional account, you have to link it to Steam: <a href='" +
                                    config.WWW_URL + "/account/link'>" +
                                    config.WWW_URL + "/account/link</a>.<br>If you need an exception, please contact an "
                                                     "admin or moderator on the forums", fatal=True)
            return False

        if response.get("result", "") == "fraudulent":
            self._logger.info("Banning player %s for fraudulent looking login.", player_id)
            await self.send_warning("Fraudulent login attempt detected. As a precautionary measure, your account has been "
                                    "banned permanently. Please contact an admin or moderator on the forums if you feel this is "
                                    "a false positive.",
                                    fatal=True)

            async with self._db.acquire() as conn:
                try:
                    ban_reason = "Auto-banned because of fraudulent login attempt"
                    ban_level = "GLOBAL"
                    await conn.execute(
                        ban.insert().values(
                            player_id=player_id,
                            author_id=player_id,
                            reason=ban_reason,
                            level=ban_level,
                        )
                    )
                except pymysql.MySQLError as e:
                    raise ClientError("Banning failed: {}".format(e))

            return False

        return response.get("result", "") == "honest"

    @handler("ask_session")
    @public
    async def command_ask_session(self, message):
        user_agent = message.get("user_agent")
        version = message.get("version")
        self._set_user_agent_and_version(user_agent, version)

        if await self._check_version():
            await self.send({"command": "session", "session": self.session})

    @handler("hello")
    @public
    async def command_hello(self, message):
        login = message["login"].strip()
        password = message["password"]

        async with self._db.acquire() as conn:
            player_id, login, steamid = await self.check_user_login(conn, login, password)
            metrics.user_logins.labels("success").inc()

            await conn.execute(
                t_login.update().where(
                    t_login.c.id == player_id
                ).values(
                    ip=self.address.host,
                    user_agent=self.user_agent,
                    last_login=func.now()
                )
            )

            conforms_policy = await self.check_policy_conformity(
                player_id, message["unique_id"], self.session,
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
                await conn.execute(
                    "UPDATE anope.anope_db_NickCore SET pass = %s WHERE display = %s",
                    (irc_pass, login)
                )
            except (pymysql.OperationalError, pymysql.ProgrammingError):
                self._logger.error("Failure updating NickServ password for %s", login)

        self.player = Player(
            login=str(login),
            session=self.session,
            player_id=player_id,
            lobby_connection=self
        )

        old_player = self.player_service.get_player(self.player.id)
        if old_player:
            self._logger.debug("player {} already signed in: {}".format(self.player.id, old_player))
            if old_player.lobby_connection is not None:
                with contextlib.suppress(DisconnectedError):
                    await old_player.lobby_connection.send_warning(
                        "You have been signed out because you signed in elsewhere.",
                        fatal=True
                    )

        await self.player_service.fetch_player_data(self.player)

        self.player_service[self.player.id] = self.player
        self.authenticated = True

        # Country
        # -------
        self.player.country = self.geoip_service.country(self.address.host)

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
                select([
                    friends_and_foes.c.subject_id,
                    friends_and_foes.c.status
                ]).where(
                    friends_and_foes.c.user_id == self.player.id
                )
            )

            async for row in result:
                target_id, status = row["subject_id"], row["status"]
                if status == "FRIEND":
                    friends.append(target_id)
                else:
                    foes.append(target_id)

        self.player.friends = set(friends)
        self.player.foes = set(foes)

        channels = []
        if self.player.is_moderator():
            channels.append("#moderators")

        if self.player.clan is not None:
            channels.append(f"#{self.player.clan}_clan")

        json_to_send = {
            "command": "social",
            "autojoin": channels,
            "channels": channels,
            "friends": friends,
            "foes": foes,
            "power": self.player.power()
        }
        await self.send(json_to_send)

        await self.send_game_list()

    @handler("restore_game_session")
    async def command_restore_game_session(self, message):
        assert self.player is not None

        game_id = int(message.get("game_id"))

        # Restore the player's game connection, if the game still exists and is live
        if not game_id or game_id not in self.game_service:
            await self.send_warning("The game you were connected to no longer exists")
            return

        game: "Game" = self.game_service[game_id]
        if game.state is not GameState.LOBBY and game.state is not GameState.LIVE:
            await self.send_warning("The game you were connected to is no longer available")
            return

        self._logger.debug("Restoring game session of player %s to game %s", self.player, game)
        self.game_connection = GameConnection(
            self.protocol,
            self.address,
            database=self._db,
            game=game,
            player=self.player,
            player_service=self.player_service,
            games=self.game_service,
            state=GameConnectionState.CONNECTED_TO_HOST
        )

        game.add_game_connection(self.game_connection)
        self.player.state = PlayerState.PLAYING
        self.player.game = game

    @handler("avatar", action="list_avatar")
    async def command_avatar_list_avatar(self, message):
        avatarList = []

        async with self._db.acquire() as conn:
            result = await conn.execute(
                select([
                    avatars_list.c.url,
                    avatars_list.c.tooltip
                ]).select_from(
                    avatars.outerjoin(
                        avatars_list
                    )
                ).where(
                    avatars.c.idUser == self.player.id
                )
            )

            async for row in result:
                avatar = {"url": row["url"], "tooltip": row["tooltip"]}
                avatarList.append(avatar)

            if avatarList:
                await self.send({"command": "avatar", "avatarlist": avatarList})

    @handler("avatar", action="select")
    async def command_avatar_select(self, message):
        avatar_url = message["avatar"]

        async with self._db.acquire() as conn:
            if avatar_url is not None:
                result = await conn.execute(
                    select([
                        avatars_list.c.id, avatars_list.c.tooltip
                    ]).select_from(
                        avatars.join(avatars_list)
                    ).where(
                        and_(
                            avatars_list.c.url == avatar_url,
                            avatars.c.idUser == self.player.id
                        )
                    )
                )
                row = await result.fetchone()
                if not row:
                    return

            await conn.execute(
                avatars.update().where(
                    avatars.c.idUser == self.player.id
                ).values(
                    selected=0
                )
            )
            self.player.avatar = None

            if avatar_url is not None:
                await conn.execute(
                    avatars.update().where(
                        and_(
                            avatars.c.idUser == self.player.id,
                            avatars.c.idAvatar == row[avatars_list.c.id]
                        )
                    ).values(
                        selected=1
                    )
                )
                self.player.avatar = {
                    "url": avatar_url,
                    "tooltip": row[avatars_list.c.tooltip]
                }
            self.player_service.mark_dirty(self.player)

    @handler("avatar")
    async def command_avatar_other(self, message):
        raise KeyError("invalid action")

    @handler("game_host")
    async def command_game_host(self, message):
        """Host a new custom game lobby"""
        assert isinstance(self.player, Player)

        if self._attempted_connectivity_test:
            raise ClientError("Cannot join game. Please update your client to the newest version.")

        await self.abort_connection_if_banned()

        visibility = VisibilityState(message["visibility"])
        title = message.get("title") or f"{self.player.login}'s game"

        try:
            title.encode("ascii")
        except UnicodeEncodeError:
            await self.send({
                "command": "notice",
                "style": "error",
                "text": "Non-ascii characters in game name detected."
            })
            return

        mod = message.get("mod") or FeaturedModType.FAF
        mapname = message.get("mapname") or "scmp_007"
        password = message.get("password")
        game_mode = mod.lower()
        rating_min = message.get("rating_min")
        rating_max = message.get("rating_max")
        enforce_rating_range = bool(message.get("enforce_rating_range", False))
        if rating_min is not None:
            rating_min = float(rating_min)
        if rating_max is not None:
            rating_max = float(rating_max)

        game = self.game_service.create_game(
            visibility=visibility,
            game_mode=game_mode,
            host=self.player,
            name=title,
            mapname=mapname,
            password=password,
            rating_type=RatingType.GLOBAL,
            displayed_rating_range=InclusiveRange(rating_min, rating_max),
            enforce_rating_range=enforce_rating_range
        )
        await self.launch_game(game, is_host=True)

    @handler("game_join")
    async def command_game_join(self, message):
        """
        Join an existing custom game lobby
        """
        assert isinstance(self.player, Player)

        if self._attempted_connectivity_test:
            raise ClientError("Cannot join game. Please update your client to the newest version.")

        await self.abort_connection_if_banned()

        uuid = int(message["uid"])
        password = message.get("password")

        self._logger.debug("joining: %d with pw: %s", uuid, password)
        try:
            game = self.game_service[uuid]
        except KeyError:
            await self.send({
                "command": "notice",
                "style": "info",
                "text": "The host has left the game."
            })
            return

        if not game or game.state is not GameState.LOBBY:
            self._logger.debug("Game not in lobby state: %s state %s", game, game.state)
            await self.send({
                "command": "notice",
                "style": "info",
                "text": "The game you are trying to join is not ready."
            })
            return

        if game.init_mode != InitMode.NORMAL_LOBBY:
            raise ClientError("The game cannot be joined in this way.")

        if game.password != password:
            await self.send({
                "command": "notice",
                "style": "info",
                "text": "Bad password (it's case sensitive)."
            })
            return

        await self.launch_game(game, is_host=False)

    @handler("game_matchmaking")
    async def command_game_matchmaking(self, message):
        """Join or leave a matchmaker queue"""
        queue_name = str(
            message.get("queue_name") or message.get("mod", "ladder1v1")
        )
        state = str(message["state"])

        if self._attempted_connectivity_test:
            raise ClientError("Cannot host game. Please update your client to the newest version.")

        if state == "stop":
            self.ladder_service.cancel_search(self.player, queue_name)
            return

        if state == "start":
            assert self.player is not None
            # Faction can be either the name (e.g. 'uef') or the enum value (e.g. 1)
            self.player.faction = message["faction"]

            # TODO: Put player parties here
            self.ladder_service.start_search(
                [self.player],
                queue_name=queue_name
            )

    async def launch_game(
        self,
        game,
        is_host=False,
        options=GameLaunchOptions(),
    ):
        assert self.player is not None
        # TODO: Fix setting up a ridiculous amount of cyclic pointers here
        if self.game_connection:
            await self.game_connection.abort("Player launched a new game")

        if is_host:
            game.host = self.player

        self.game_connection = GameConnection(
            self.protocol,
            self.address,
            database=self._db,
            game=game,
            player=self.player,
            player_service=self.player_service,
            games=self.game_service
        )

        self.player.state = PlayerState.HOSTING if is_host else PlayerState.JOINING
        self.player.game = game
        cmd = {
            "command": "game_launch",
            "args": ["/numgames", self.player.game_count[game.rating_type]],
            "uid": game.id,
            "mod": game.game_mode,
            "name": game.name,
            "init_mode": game.init_mode.value,
            **options._asdict()
        }

        await self.send({k: v for k, v in cmd.items() if v is not None})

    @handler("modvault")
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

            elif type == "like":
                canLike = True
                uid = message["uid"]
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
                raise ValueError("invalid type argument")

    @handler("ice_servers")
    async def command_ice_servers(self, message):
        if not self.player:
            return

        ttl = config.TWILIO_TTL
        ice_servers = self.coturn_generator.server_tokens(
            username=self.player.id,
            ttl=ttl
        )

        if self.nts_client:
            ice_servers += await self.nts_client.server_tokens(ttl=ttl)

        await self.send({
            "command": "ice_servers",
            "ice_servers": ice_servers,
            "ttl": ttl
        })

    async def kick(self):
        await self.send({
            "command": "notice",
            "style": "kick",
        })
        await self.abort()

    async def send_game_list(self):
        await self.send({
            "command": "game_info",
            "games": [game.to_dict() for game in self.game_service.open_games]
        })

    async def send_updated_achievements(self, updated_achievements):
        await self.send({
            "command": "updated_achievements",
            "updated_achievements": updated_achievements
        })

    async def send_warning(self, message: str, fatal: bool = False):
        """
        Display a warning message to the client
        :param message: Warning message to display
        :param fatal: Whether or not the warning is fatal.
                      If the client receives a fatal warning it should disconnect
                      and not attempt to reconnect.
        :return: None
        """
        await self.send({
            "command": "notice",
            "style": "info" if not fatal else "error",
            "text": message
        })
        if fatal:
            await self.abort(message)

    async def send(self, message):
        """Send a message and wait for it to be sent."""
        self.write(message)
        await self.protocol.drain()

    def write(self, message):
        """Write a message into the send buffer."""
        self._logger.log(TRACE, ">> %s: %s", self.get_user_identifier(), message)
        self.protocol.write_message(message)

    async def on_connection_lost(self):
        async def nop(*args, **kwargs):
            return
        self.send = nop
        if self.game_connection:
            self._logger.debug(
                "Lost lobby connection killing game connection for player %s",
                self.game_connection.player.id
            )
            await self.game_connection.on_connection_lost()

        if self.player:
            self._logger.debug(
                "Lost lobby connection removing player %s", self.player.id
            )
            await self.ladder_service.on_connection_lost(self.player)
            self.player_service.remove_player(self.player)

    async def abort_connection_if_banned(self):
        async with self._db.acquire() as conn:
            now = datetime.utcnow()
            result = await conn.execute(
                select([lobby_ban.c.reason, lobby_ban.c.expires_at])
                .where(lobby_ban.c.idUser == self.player.id)
                .order_by(lobby_ban.c.expires_at.desc())
            )

            data = await result.fetchone()
            if data is None:
                return

            ban_expiry = data[ban.c.expires_at]
            ban_reason = data[ban.c.reason]
            if now < ban_expiry:
                self._logger.debug("Aborting connection of banned user: %s, %s, %s",
                                   self.player.id, self.player.login, self.session)
                raise BanError(ban_expiry, ban_reason)
