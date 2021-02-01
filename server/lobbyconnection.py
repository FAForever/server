import asyncio
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
import pymysql
from sqlalchemy import and_, func, select

import server.metrics as metrics
from server.db import FAFDatabase

from .abc.base_game import GameConnectionState, InitMode
from .config import TRACE, config
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
from .exceptions import AuthenticationError, BanError, ClientError
from .factions import Faction
from .game_service import GameService
from .gameconnection import GameConnection
from .games import FeaturedModType, GameState, VisibilityState
from .geoip_service import GeoIpService
from .ice_servers.coturn import CoturnHMAC
from .ice_servers.nts import TwilioNTS
from .ladder_service import LadderService
from .party_service import PartyService
from .player_service import PlayerService
from .players import Player, PlayerState
from .protocol import DisconnectedError, Protocol
from .rating import InclusiveRange, RatingType
from .types import Address, GameLaunchOptions


@with_logger
class LobbyConnection:
    @timed()
    def __init__(
        self,
        database: FAFDatabase,
        game_service: GameService,
        players: PlayerService,
        nts_client: Optional[TwilioNTS],
        geoip: GeoIpService,
        ladder_service: LadderService,
        party_service: PartyService
    ):
        self._db = database
        self.geoip_service = geoip
        self.game_service = game_service
        self.player_service = players
        self.nts_client = nts_client
        self.coturn_generator = CoturnHMAC(config.COTURN_HOSTS, config.COTURN_KEYS)
        self.ladder_service = ladder_service
        self.party_service = party_service
        self._authenticated = False
        self.player = None  # type: Player
        self.game_connection = None  # type: GameConnection
        self.peer_address = None  # type: Optional[Address]
        self.session = int(random.randrange(0, 4294967295))
        self.protocol: Protocol = None
        self.user_agent = None
        self.version = None

        self._attempted_connectivity_test = False

        self._logger.debug("LobbyConnection initialized")

    @property
    def authenticated(self):
        return self._authenticated

    def get_user_identifier(self) -> str:
        """For logging purposes"""
        if self.player:
            return self.player.login

        return str(self.session)

    async def on_connection_made(self, protocol: Protocol, peername: Address):
        self.protocol = protocol
        self.peer_address = peername
        metrics.server_connections.inc()

    async def abort(self, logspam=""):
        self._authenticated = False
        if self.player:
            self._logger.warning(
                "Client %s dropped. %s", self.player.login, logspam
            )
            self.player_service.remove_player(self.player)
            self.player = None
        else:
            self._logger.warning(
                "Aborting %s. %s", self.peer_address.host, logspam
            )
        if self.game_connection:
            await self.game_connection.abort()

        await self.protocol.close()

    async def ensure_authenticated(self, cmd):
        if not self._authenticated:
            if cmd not in ["hello", "ask_session", "create_account", "ping", "pong", "Bottleneck"]:  # Bottleneck is sent by the game during reconnect
                metrics.unauth_messages.labels(cmd).inc()
                await self.abort("Message invalid for unauthenticated connection: %s" % cmd)
                return False
        return True

    async def on_message_received(self, message):
        """
        Dispatches incoming messages
        """
        self._logger.log(TRACE, "<< %s: %s", self.get_user_identifier(), message)

        try:
            cmd = message["command"]
            if not await self.ensure_authenticated(cmd):
                return
            target = message.get("target")
            if target == "game":
                if not self.game_connection:
                    return

                await self.game_connection.handle_action(cmd, message.get("args", []))
                return

            if target == "connectivity" and message.get("command") == "InitiateTest":
                self._attempted_connectivity_test = True
                raise ClientError("Your client version is no longer supported. Please update to the newest version: https://faforever.com")

            handler = getattr(self, "command_{}".format(cmd))
            await handler(message)

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
            await self.abort("Garbage command: {}".format(message))
        except ConnectionError as e:
            # Propagate connection errors to the ServerContext error handler.
            raise e
        except Exception as ex:  # pragma: no cover
            await self.send({"command": "invalid"})
            self._logger.exception(ex)
            await self.abort("Error processing command")

    async def command_ping(self, msg):
        await self.send({"command": "pong"})

    async def command_pong(self, msg):
        pass

    async def command_create_account(self, message):
        raise ClientError("FAF no longer supports direct registration. Please use the website to register.", recoverable=True)

    async def command_coop_list(self, message):
        """ Request for coop map list"""
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

    async def command_matchmaker_info(self, message):
        await self.send({
            "command": "matchmaker_info",
            "queues": [queue.to_dict() for queue in self.ladder_service.queues.values()]
        })

    async def send_game_list(self):
        await self.send({
            "command": "game_info",
            "games": [game.to_dict() for game in self.game_service.open_games]
        })

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
        action = message["action"]

        if action == "closeFA":
            if await self.player_service.has_permission_role(
                self.player, "ADMIN_KICK_SERVER"
            ):
                player = self.player_service[message["user_id"]]
                if player:
                    self._logger.info(
                        "Administrative action: %s closed game for %s",
                        self.player, player
                    )
                    with contextlib.suppress(DisconnectedError):
                        await player.send_message({
                            "command": "notice",
                            "style": "kill",
                        })

        elif action == "closelobby":
            if await self.player_service.has_permission_role(
                self.player, "ADMIN_KICK_SERVER"
            ):
                player = self.player_service[message["user_id"]]
                if player and player.lobby_connection is not None:
                    self._logger.info(
                        "Administrative action: %s closed client for %s",
                        self.player, player
                    )
                    with contextlib.suppress(DisconnectedError):
                        await player.lobby_connection.kick()

        elif action == "broadcast":
            message_text = message.get("message")
            if not message_text:
                return
            if await self.player_service.has_permission_role(
                self.player, "ADMIN_BROADCAST_MESSAGE"
            ):
                for player in self.player_service:
                    # Check if object still exists:
                    # https://docs.python.org/3/library/weakref.html#weak-reference-objects
                    if player.lobby_connection is not None:
                        with contextlib.suppress(DisconnectedError):
                            player.lobby_connection.write_warning(message_text)

                self._logger.info(
                    "%s broadcasting message to all players: %s",
                    self.player.login, message_text
                )
        elif action == "join_channel":
            if await self.player_service.has_permission_role(
                self.player, "ADMIN_JOIN_CHANNEL"
            ):
                user_ids = message["user_ids"]
                channel = message["channel"]

                for user_id in user_ids:
                    player = self.player_service[user_id]
                    if player:
                        player.write_message({
                            "command": "social",
                            "autojoin": [channel]
                        })

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
        metrics.user_connections.labels(str(self.user_agent), str(self.version)).dec()
        self.user_agent = user_agent

        # only count a new version if it previously wasn't set
        # to avoid double counting
        if self.version is None and version is not None:
            metrics.user_agent_version.labels(str(version)).inc()
        self.version = version

        metrics.user_connections.labels(str(self.user_agent), str(self.version)).inc()

    async def _check_user_agent(self):
        if not self.user_agent or "downlords-faf-client" not in self.user_agent:
            await self.send_warning(
                "You are using an unofficial client version! "
                "Some features might not work as expected. "
                "If you experience any problems please download the latest "
                "version of the official client from "
                f'<a href="{config.WWW_URL}">{config.WWW_URL}</a>'
            )

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
                    ip=self.peer_address.host,
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
                    old_player.lobby_connection.write_warning(
                        "You have been signed out because you signed in "
                        "elsewhere.",
                        fatal=True
                    )

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

    async def command_restore_game_session(self, message):
        assert self.player is not None

        game_id = int(message.get("game_id"))

        # Restore the player's game connection, if the game still exists and is live
        if not game_id or game_id not in self.game_service:
            await self.send_warning("The game you were connected to does no longer exist")
            return

        game = self.game_service[game_id]  # type: Game
        if game.state is not GameState.LOBBY and game.state is not GameState.LIVE:
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
        self.player.game = game

    async def command_ask_session(self, message):
        user_agent = message.get("user_agent")
        version = message.get("version")
        self._set_user_agent_and_version(user_agent, version)
        await self._check_user_agent()
        await self.send({"command": "session", "session": self.session})

    async def command_avatar(self, message):
        action = message["action"]

        if action == "list_avatar":
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

        elif action == "select":
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
        else:
            raise KeyError("invalid action")

    def ice_only(func):
        """
        Ensures that a handler function is not invoked from a non ICE client.
        """
        @wraps(func)
        async def wrapper(self, message):
            if self._attempted_connectivity_test:
                raise ClientError("Cannot join game. Please update your client to the newest version.")
            return await func(self, message)
        return wrapper

    def player_idle(state_text):
        """
        Ensures that a handler function is not invoked unless the player state
        is IDLE.
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(self, message):
                if self.player.state != PlayerState.IDLE:
                    raise ClientError(
                        f"Can't {state_text} while in state "
                        f"{self.player.state.name}",
                        recoverable=True
                    )
                return await func(self, message)
            return wrapper
        return decorator

    @ice_only
    @player_idle("join a game")
    async def command_game_join(self, message):
        """
        We are going to join a game.
        """
        assert isinstance(self.player, Player)

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

    @ice_only
    async def command_game_matchmaking(self, message):
        queue_name = str(
            message.get("queue_name") or message.get("mod", "ladder1v1")
        )
        state = str(message["state"])

        if state == "stop":
            self.ladder_service.cancel_search(self.player, queue_name)
            return

        party = self.party_service.get_party(self.player)

        if self.player is not party.owner:
            raise ClientError(
                "Only the party owner may enter the party into a queue.",
                recoverable=True
            )

        for member in party:
            player = member.player
            if player.state not in (
                PlayerState.IDLE,
                PlayerState.SEARCHING_LADDER
            ):
                raise ClientError(
                    f"Can't join a queue while {player.login} is in state "
                    f"{player.state.name}",
                    recoverable=True
                )

        if state == "start":
            players = party.players
            if len(players) > self.ladder_service.queues[queue_name].team_size:
                raise ClientError(
                    "Your party is too large to join that queue!",
                    recoverable=True
                )

            # TODO: Remove this legacy behavior, use party instead
            if "faction" in message:
                party.set_factions(
                    self.player,
                    [Faction.from_value(message["faction"])]
                )

            self.ladder_service.start_search(
                players,
                queue_name=queue_name,
                on_matched=party.on_matched
            )

    @ice_only
    @player_idle("host a game")
    async def command_game_host(self, message):
        assert isinstance(self.player, Player)

        await self.abort_connection_if_banned()

        visibility = VisibilityState(message["visibility"])
        title = message.get("title") or f"{self.player.login}'s game"
        if not title.isascii():
            raise ClientError("Title must contain only ascii characters.")

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
            "args": ["/numgames", self.player.game_count[game.rating_type]],
            "uid": game.id,
            "mod": game.game_mode,
            # Following parameters may not be used by the client yet. They are
            # needed for setting up auto-lobby style matches such as ladder, gw,
            # and team machmaking where the server decides what these game
            # options are. Currently, options for ladder are hardcoded into the
            # client.
            "name": game.name,
            "init_mode": game.init_mode.value,
            "rating_type": game.rating_type,
            **options._asdict()
        }

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

    @player_idle("invite a player")
    async def command_invite_to_party(self, message):
        recipient = self.player_service.get_player(message["recipient_id"])
        if recipient is None:
            # TODO: Client localized message
            raise ClientError("The invited player doesn't exist", recoverable=True)

        if self.player.id in recipient.foes:
            return

        self.party_service.invite_player_to_party(self.player, recipient)

    @player_idle("join a party")
    async def command_accept_party_invite(self, message):
        sender = self.player_service.get_player(message["sender_id"])
        if sender is None:
            # TODO: Client localized message
            raise ClientError("The inviting player doesn't exist", recoverable=True)

        await self.party_service.accept_invite(self.player, sender)

    @player_idle("kick a player")
    async def command_kick_player_from_party(self, message):
        kicked_player = self.player_service.get_player(message["kicked_player_id"])
        if kicked_player is None:
            # TODO: Client localized message
            raise ClientError("The kicked player doesn't exist", recoverable=True)

        await self.party_service.kick_player_from_party(self.player, kicked_player)

    async def command_leave_party(self, _message):
        self.ladder_service.cancel_search(self.player)
        await self.party_service.leave_party(self.player)

    async def command_set_party_factions(self, message):
        factions = set(Faction.from_value(v) for v in message["factions"])

        if not factions:
            raise ClientError(
                "You must select at least one faction.",
                recoverable=True
            )

        self.party_service.set_factions(self.player, list(factions))

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

    def write_warning(self, message: str, fatal: bool = False):
        """
        Like send_warning, but does not await the data to be sent.
        """
        self.write({
            "command": "notice",
            "style": "info" if not fatal else "error",
            "text": message
        })
        if fatal:
            asyncio.create_task(self.abort(message))

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
            await self.party_service.on_player_disconnected(self.player)

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
