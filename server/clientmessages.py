from enum import Enum, auto
import functools
from typing import NamedTuple, Optional


class Target(Enum):
    """
    Valid entries for the `'target'` field in a message from the client.
    """

    none = 0
    game = 1
    connectivity = 2  # deprecated


class ActionField(Enum):
    """
    Valid entries for the `'action'` field in a message from the client.
    """

    list_avatar = 1
    select = 2


class CommandField(Enum):
    """
    Valid entries for the required `'command'` field in a message from the client.
    """

    admin = auto()
    ask_session = auto()
    avatar = auto()
    coop_list = auto()
    create_account = auto()
    game_host = auto()
    game_join = auto()
    game_matchmaking = auto()
    hello = auto()
    ice_servers = auto()
    matchmaker_info = auto()
    modvault = auto()
    ping = auto()
    pong = auto()
    restore_game_session = auto()
    social_add = auto()
    social_remove = auto()
    Bottleneck = auto()


class Message:
    """
    Common base class for parsed messages from and to the client.
    """

    pass


class MessageFromClient(Message):
    """
    Common base class for parsed messages from the client.
    """

    pass


class MessageToClient(Message):
    """
    Common base class for parsed messages to the client.
    """

    pass


class LobbyTargetMessage(MessageFromClient):
    """
    Common base class for messages without `target` entry  or entry `'none'`.

    To be handled by a `LobbyConnection`.
    """

    @staticmethod
    def build(lobbyconnection, message):
        command = MessageParser.parse_command(message)
        return COMMAND_TO_CLASS[command].build(message)


class ConnectivityTargetMessage(MessageFromClient):
    """
    Deprecated functionality for `target` entry `'connectivity'`.

    Will ask client to update to the newest version.
    """

    @staticmethod
    async def __init__(self, lobbyconnection=None, message=None):
        lobbyconnection.register_connectivity_test()

    async def handle(self):
        raise ClientError(
            f"Your client version is no longer supported."
            f"Please update to the newest version: https://faforever.com"
        )


class GameTargetMessage(MessageFromClient):
    """
    Common base class for messages with `target` entry `'game'`.

    To be handled by a `GameConnection`.
    """

    @staticmethod
    async def build(lobbyconnection=None, message=None):
        # need to make a distinction on command, arguments
        # should fail if passed lobbyconnection does not have a game_connection
        # message entry 'args' needs to be passed along
        # previous code:
        #   if target == 'game':
        #       if not self.game_connection:
        #           return
        #
        #       await self.game_connection.handle_action(cmd, message.get('args', []))
        #       return
        raise NotImplementedError("TODO")


class PingMessage(LobbyTargetMessage):
    """
    Returns a 'PONG' message.

    Does not require the client to be authenticated.

    Required fields:

     - `command`: `ping`
    """

    command: str = "ping"
    _command_enum = CommandField.ping


class PongMessage(LobbyTargetMessage):
    """
    Does nothing.

    Does not require the client to be authenticated.

    Required fields:

     - `command`: `pong`
    """

    command: str = "pong"

    @classmethod
    def build(cls, message):
        return PongMessage()


class AccountCreationMessage(LobbyTargetMessage):
    """

    Required fields:

     - `command`: `create_account`
    """

    command: str = "create_account"

    @classmethod
    def build(cls, message):
        return AccountCreationMessage()


class CoopListMessage(NamedTuple, LobbyTargetMessage):
    """
    Asks server for the list of coop maps.

    Requires the client to be authenticated.

    Required fields:

     - `command`: `coop_list`
    """

    commad: str = "coop_list"

    @classmethod
    def build(cls, message):
        return CoopListMessage()


class MatchmakerInfoMessage(LobbyTargetMessage):
    """
    TODO: Description

    Requires the client to be authenticated.

    Required fields:

     - `command`: `matchmaker_info`
    """

    command: str = "matchmaker_info"
    _command_enum = CommandField.matchmaker_info


class SocialRemoveMessage(NamedTuple, LobbyTargetMessage):
    """
    Remove someone from your friend list or foe list.

    Requires the client to be authenticated.

    Required fields:  

      - `command`: `social_remove`  

    And at least one of the following:

     - `friend`: `id` of player to remove from friend list
     - `foe`: `id` of player to remove from foe list

    If both `friend` and `foe` are specified, only the friend will be removed.
    """

    command: str
    id_to_remove: int

    @classmethod
    def build(cls, message):
        if "friend" in message:
            id_to_remove = message["friend"]
        elif "foe" in message:
            id_to_remove = message["foe"]
        else:
            raise MessageParsingError(
                f"Message to remove friend or foe "
                f"must contain at least one of 'friend' or 'foe' fields. "
                f"Offending message: {message}."
            )

        return cls("social_remove", id_to_remove)


class SocialAddMessage(NamedTuple, LobbyTargetMessage):
    """
    Add someone to your friend list or foe list.

    Requires the client to be authenticated.

    Required fields:  

      - `command`: `social_add`  

    And at least one of the following:

     - `friend`: `id` of player to add to friend list
     - `foe`: `id` of player to add to foe list

    If both `friend` and `foe` are specified, only the friend will be added.
    """

    command: str
    id_to_add: int
    adding_a_friend: bool

    @classmethod
    def build(cls, message):
        if "friend" in message:
            adding_a_friend = True
            id_to_add = message["friend"]
        elif "foe" in message:
            adding_a_friend = False
            id_to_add = message["foe"]
        else:
            raise MessageParsingError(
                f"Message to add friend or foe "
                f"must contain at least one of 'friend' or 'foe' fields. "
                f"Offending message: {message}."
            )

        return cls("social_add", id_to_add, adding_a_friend)


class BottleneckMessage(LobbyTargetMessage):
    """
    Not yet implemented
    """

    def __init__(self, lobbyconnection=None, message=None):
        raise NotImplementedError


class AdminMessage(NamedTuple, LobbyTargetMessage):
    """
    Various admin functionality crammed into a single command

    Requires the client to be authenticated.

    Required fields:  

      - `command`: `admin`  
      - `action`: one of `closeFA`, `closelobby`,`broadcast`, `join_channel`

    Required if `action` is `closeFA` or `closelobby`:

     - `user_id`: user id of target player

    Optional if `action` is `closelobby`:

     - `ban`: json containing ban details

    Ban json should contain fiels `reason`, `duration`, and `period`.
    Defaults are currently `Unspecified`, 1, and `SECOND`.
    Admissible periods are `SECOND`, `DAY`, `WEEK`, `MONTH`.

    Required if `action` is `broadcast`:

     - `message`: message to broadcast

    Required if `action` is `join_channel`:

     - `channel`: ? probably some kind of channel id
     - `user_ids`: ? probably ids of all users that will join the channel?
    """

    command: str
    action: str
    target_user_id: Optional[int]
    ban_data: Optional[dict]
    broadcast_message: Optional[str]
    channel: Optional[str]
    channel_users: Optional[list]

    @classmethod
    def build(cls, message):
        action = message.get("action")
        if action not in ["closeFA", "closelobby", "broadcast", "join_channel"]:
            raise MessageParsingError(
                f"Message for command 'admin' must contain field 'action' with one of 'closeFA', 'closelobby', 'broadcast', 'join_channel'. Offending message: {message}."
            )

        target_user_id = message.get("user_id")

        ban_data = message.get("ban")
        if ban_data:
            ban_data.setdefault("reason", "Unspecified")
            ban_data.setdefault("duration", 1)
            ban_data.setdefault("period", "SECOND")

            ban_data["duration"] = int(
                ban_data["duration"]
            )  # NOTE: copied from LobbyConnection.command_admin, unsure if necessary
            ban_data["period"] = ban_data["period"].upper()

        broadcast_message = message.get("message")

        channel_users = message.get("user_ids")
        channel = message.get("channel")

        if action == "closeFA" and target_user_id is None:
            raise MessageParsingError(
                f"Command 'admin' with action `closeFA` "
                f"needs `user_id` to be id of target player. "
                f"Offending message: {message}."
            )

        if action == "closelobby" and target_user_id is None:
            raise MessageParsingError(
                f"Command 'admin' with action `closelobby` "
                f"needs `user_id` to be id of target player. "
                f"Offending message: {message}."
            )

        have_channel_and_users = channel is not None and channel_users is not None
        if action == "join_channel" and not have_channel_and_users:
            raise MessageParsingError(
                f"Command 'admin' with action `join_channel` "
                f"needs fields `user_ids` and `channel`. "
                f"Offending message: {message}."
            )

        return cls(
            "admin",
            action,
            target_user_id,
            ban_data,
            broadcast_message,
            channel,
            channel_users,
        )


class HelloMessage(LobbyTargetMessage):
    """
    Not yet implemented
    """

    def __init__(self, lobbyconnection=None, message=None):
        raise NotImplementedError


class GameMatchmakingMessage(NamedTuple, LobbyTargetMessage):
    """
    Queue up for matchmaking or cancel matchmaking search.

    Requires the client to be authenticated.

    Required fields:  

      - `command`: `game_matchmaking`  
      - `state`: `start` or `stop`

    Optional fields:
      - `mod`: Currently discarded. If `state` is `start`, this  might at some
        point specify in which queue to start matchmaking. Default `ladder1v1`
        if empty.
    """

    command: str
    mod: str
    state: str

    @classmethod
    def build(cls, message):
        # NOTE: copied str conversions from previous
        # lobbyconnection.LobbyConnection.command_game_matchmaking,
        # but not sure if needed.
        mod = (str(message.get("mod", "ladder1v1")),)

        if str(message.get("state")) not in ["start", "stop"]:
            raise MessageParsingError(
                f"Message with command 'game_matchmaking' "
                f"must contain the field 'state' set to 'start' or 'stop'. "
                f"Offending message: {message}."
            )
        state = str(message["state"])

        return cls("game_matchmaking", mod, state)


class GameHostMessage(NamedTuple, LobbyTargetMessage):
    """
    Host a game.

    Requires the client to be authenticated.

    Required fields:  

      - `command`: `game_matchmaking`  

    Optional fields:
      - `title`: title of the game (default: set by LobbyConnection.command_game_host)
      - `mod`: (default: `faf`)
      - `mapname`: (default `scmp_007`)
      - `password`: (default: none)
    password: Optional[str]

      - `visibility`: according to games.VisibilityState
    """

    command: str
    title: str
    mod: str
    mapname: str
    password: Optional[str]
    visibility: str

    @classmethod
    def build(cls, message):
        title = message.get("title")
        mod = message.get("mod", "faf")
        mapname = message.get("mapname", "scmp_007")
        password = message.get("password")
        visibility = message.get("visibility")

        return cls("game_host", title, mod, mapname, password, visibility)


class GameJoinMessage(NamedTuple, LobbyTargetMessage):
    """
    Join a game.

    Requires the client to be authenticated.

    Required fields:  

      - `command`: `game_join`  
      - `uid`: id of game to join

    Optional fields:
      - `password`: (default: none)
    """

    command: str
    uid: int
    password: Optional[str]

    @classmethod
    def build(cls, message):
        try:
            uid = int(message["uid"])
        except (KeyError, ValueError):
            raise MessageParsingError(
                f"Command 'game_join' needs field 'uid' to be an integer. "
                f"Offending message: {message}"
            )

        password = message.get("password")

        return cls("game_join", uid, password)


class ICEServersMessage(LobbyTargetMessage):
    """
    Not yet implemented
    """

    def __init__(self, lobbyconnection=None, message=None):
        raise NotImplementedError


class ModvaultMessage(LobbyTargetMessage):
    """
    Not yet implemented
    """

    def __init__(self, lobbyconnection=None, message=None):
        raise NotImplementedError


class RestoreGameSessionMessage(LobbyTargetMessage):
    """
    Not yet implemented
    """

    def __init__(self, lobbyconnection=None, message=None):
        raise NotImplementedError


class AvatarMessage(NamedTuple, LobbyTargetMessage):
    """
    Asks server to either return a list of avatars for the current user
    or select a new avatar.

    Requires the client to be authenticated.

    Required fields:  

      - `command`: `avatar`  
      - `action`: `select` or `list_avatar` (default: `list_avatar`)
      - `avatar`: url of new avatar or `null` for default avatar (?) (default: `null`)
    """

    command: str
    action: str
    url: Optional[str]

    @classmethod
    def build(cls, message):
        avatar_url = message.get("avatar", None)
        if avatar_url == "null":
            avatar_url = None

        action = message.get("action", "list_avatar")
        if action not in ["select", "list_avatar"]:
            raise MessageParsingError(
                f"Command 'avatar' needs field 'action' "
                f"to be either 'select' or 'list_avatar'. "
                f"Offending message: {message}"
            )

        return cls("avatar", action, avatar_url)


class AskSessionMessage(LobbyTargetMessage):
    """
    TODO: Description

    Requires the client to be authenticated.

    Required fields:

     - `command`: `ask_session`

    Expected fields:
     - `user_agent`: TODO probably `'downlords-faf-client'`
     - `version`: TODO probably version number of downlords-faf-client
     """

    def __init__(self, lobbyconnection=None, message=None):
        self._connection = lobbyconnection
        self._message = message
        self._command = CommandField.ask_session

        self._user_agent = message.get("user_agent")
        self._version = message.get("version")

    async def handle(self):
        self._connection.command_ask_session()


class MessageParser:
    """
    Assembles a `Message` object from received json-like dict.
    """

    @staticmethod
    def parse(lobbyconnection, message):
        if "command" not in message:
            raise MessageParsingError(
                f"Message did not contain required 'command' field. "
                f"Offending message: {message}"
            )
        target = Target[message.get("target", "none")]

        if target is Target.game:
            return GameTargetMessage.build(lobbyconnection, message)
        elif target is Target.connectivity:
            return ConnectivityTargetMessage(lobbyconnection, message)
        else:
            return LobbyTargetMessage.build(lobbyconnection, message)

    @staticmethod
    def parse_command(message):
        if "command" not in message:
            raise MessageParsingError(
                f"Message did not contain required 'command' field. "
                f"Offending message: {message}"
            )
        try:
            return CommandField[message["command"]]
        except KeyError:
            raise MessageParsingError(
                f"'command' field of message {message} is invalid."
            )


class MessageParsingError(Exception):
    """
    Raised if trying to parse a message with invalid format.
    """

    pass


COMMAND_TO_CLASS = {
    CommandField.admin: AdminMessage,
    CommandField.ask_session: AskSessionMessage,
    CommandField.avatar: AvatarMessage,
    CommandField.coop_list: CoopListMessage,
    CommandField.create_account: AccountCreationMessage,
    CommandField.game_host: GameHostMessage,
    CommandField.game_join: GameJoinMessage,
    CommandField.game_matchmaking: GameMatchmakingMessage,
    CommandField.hello: HelloMessage,
    CommandField.ice_servers: ICEServersMessage,
    CommandField.matchmaker_info: MatchmakerInfoMessage,
    CommandField.modvault: ModvaultMessage,
    CommandField.ping: PingMessage,
    CommandField.pong: PongMessage,
    CommandField.restore_game_session: RestoreGameSessionMessage,
    CommandField.social_add: SocialAddMessage,
    CommandField.social_remove: SocialRemoveMessage,
    CommandField.Bottleneck: BottleneckMessage,
}
