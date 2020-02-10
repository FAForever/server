from enum import Enum, auto
import functools
from typing import NamedTuple, Optional, Union


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
    """

    @staticmethod
    def parse(message):
        command = MessageParser.parse_command(message)
        return COMMAND_TO_CLASS[command].build(message)


class ConnectivityTargetMessage(NamedTuple, MessageFromClient):
    """Deprecated messages with `target` entry `'connectivity'` will be directed here."""
    command: Optional[str]

    @classmethod
    def build(cls, message):
        command = message.get("command")
        return cls(command)


class GameTargetMessage(NamedTuple, MessageFromClient):
    """ Messages with `target` entry `'game'` will be directed here
and passed on to a `GameConnection`.

Required fields:

  - `command`: command to be passed on to the `GameConnection`.

Optional fields:

  - `args`: list of arguments to be passed along with the command
"""

    command: str
    args: list

    @classmethod
    def build(cls, message):

        if "command" not in message:
            raise MessageParsingError(
                f"Message with target 'game' must contain field 'command'. "
                f"Offending message: {message}."
            )

        command = message["command"]
        arguments = message.get("args", [])

        return cls(command, arguments)


class PingMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:

 - `command`: `ping`
"""

    command: str = "ping"

    @classmethod
    def build(cls, message):
        return cls()


class PongMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:

 - `command`: `pong`
"""

    command: str = "pong"

    @classmethod
    def build(cls, message):
        return cls()


class AccountCreationMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:

 - `command`: `create_account`
"""

    command: str = "create_account"

    @classmethod
    def build(cls, message):
        return cls()


class CoopListMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:

 - `command`: `coop_list`
"""

    command: str = "coop_list"

    @classmethod
    def build(cls, message):
        return CoopListMessage()


class MatchmakerInfoMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:

 - `command`: `matchmaker_info`
"""

    command: str = "matchmaker_info"

    @classmethod
    def build(cls, message):
        return cls()


class SocialRemoveMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:  

  - `command`: `social_remove`  

And at least one of the following:

 - `friend`: `id` of player to remove from friend list
 - `foe`: `id` of player to remove from foe list

If both `friend` and `foe` are specified, the foe will be ignored
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
    """Required fields:  

  - `command`: `social_add`  

And at least one of the following:

 - `friend`: `id` of player to add to friend list
 - `foe`: `id` of player to add to foe list
 
If both `friend` and `foe` are specified, the `foe` will be ignored.
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


class BottleneckMessage(NamedTuple, LobbyTargetMessage):
    """TODO: Unsure what this does. Will it still be sent? How does lobbyconnection handle it?
"""

    command: str = "Bottleneck"

    @classmethod
    def build(cls, message):
        return cls()


class AdminMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:  

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
        if ban_data is not None:
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

        if action in ["closeFA", "closelobby"] and target_user_id is None:
            raise MessageParsingError(
                f"Command 'admin' with action `closeFA` or `closelobby` "
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


class HelloMessage(NamedTuple, LobbyTargetMessage):
    """TODO Description
"""

    command: str
    login: str
    password: str
    unique_id: int

    @classmethod
    def build(cls, message):
        try:
            login = message["login"].strip()
            password = message["password"]
            unique_id = message["unique_id"]
        except KeyError:
            raise MessageParsingError(
                f"Command 'hello' needs fields `login`, `password`, "
                f"and `unique_id`. "
                f"Offending message: {message}."
            )
        return cls("hello", login, password, unique_id)


class GameMatchmakingMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:  

  - `command`: `game_matchmaking`  
  - `state`: `start` or `stop`

Optional fields:
  - `faction`: faction of the player if `state` is `start`. Defailt `uef`.
    Can either be the name (e.g. 'uef') or the enum value (e.g. 1).
  - `mod`: Currently discarded. If `state` is `start`, this  might at some
    point specify in which queue to start matchmaking. Default `ladder1v1`
    if empty.
"""

    command: str
    mod: str
    state: str
    faction: Optional[Union[str, int]]

    @classmethod
    def build(cls, message):
        # NOTE: copied str conversions from previous
        # lobbyconnection.LobbyConnection.command_game_matchmaking,
        # but not sure if needed.
        mod = str(message.get("mod", "ladder1v1"))

        if str(message.get("state")) not in ["start", "stop"]:
            raise MessageParsingError(
                f"Message with command 'game_matchmaking' "
                f"must contain the field 'state' set to 'start' or 'stop'. "
                f"Offending message: {message}."
            )
        state = str(message["state"])

        faction = message.get("faction", "uef")

        return cls("game_matchmaking", mod, state, faction)


class GameHostMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:  

  - `command`: `game_matchmaking`  

Optional fields:

  - `title`: title of the game (default: set by LobbyConnection.command_game_host)  
  - `mod`: (default: `faf`)  
  - `mapname`: (default `scmp_007`)  
  - `password`: (default: none)  
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
        mod = (
            message.get("mod") or "faf"
        )  # want to choose default if mod string is empty.
        mapname = message.get("mapname", "scmp_007")
        password = message.get("password")
        visibility = message.get("visibility")

        return cls("game_host", title, mod, mapname, password, visibility)


class GameJoinMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:  

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


class ICEServersMessage(NamedTuple, LobbyTargetMessage):
    """ TODO: Description """

    command: str

    @classmethod
    def build(cls, message):
        return cls("ice_servers")


class ModvaultMessage(NamedTuple, LobbyTargetMessage):
    """ TODO: Description """

    command: str
    type_field: str
    uid: int

    @classmethod
    def build(cls, message):
        type_field = message.get("type")
        if type_field not in ["start", "like", "download"]:
            raise MessageParsingError(
                f"Command 'modvault' needs field 'type' "
                f"to be 'start', 'like', or 'download'. "
                f"Offending message: {message}"
            )

        uid = message.get("uid")
        if type_field in ["like", "download"] and uid is None:
            raise MessageParsingError(
                f"Command 'modvault' needs field 'uid' "
                f"if 'type' is 'like' or 'download'. "
                f"Offending message: {message}"
            )

        return cls("modvault", type_field, uid)


class RestoreGameSessionMessage(NamedTuple, LobbyTargetMessage):
    """ TODO Description """

    command: str
    game_id: int

    @classmethod
    def build(cls, message):
        try:
            game_id = int(message["game_id"])
        except (KeyError, ValueError):
            raise MessageParsingError(
                f"Command 'restore_game_session' needs field 'game_id' to be an integer. "
                f"Offending message: {message}"
            )

        return cls("restore_game_session", game_id)


class AvatarMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:  

  - `command`: `avatar`  
  - `action`: `select` or `list_avatar` (default: `list_avatar`)

Optional fields:

  - `avatar`: url of new avatar or `null` for default avatar (?) (default: `null`)
"""

    command: str
    action: str
    url: Optional[str]

    @classmethod
    def build(cls, message):
        avatar_url = message.get("avatar")
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


class AskSessionMessage(NamedTuple, LobbyTargetMessage):
    """Required fields:

 - `command`: `ask_session`

Expected fields:
- `user_agent`: TODO probably `'downlords-faf-client'`
- `version`: TODO probably version number of downlords-faf-client
"""

    command: str
    user_agent: str
    version: str

    @classmethod
    def build(cls, message):
        user_agent = message.get("user_agent")
        version = message.get("version")

        return cls("ask_session", user_agent, version)


class MessageParser:
    """Assembles a `Message` object from received json-like dict."""

    @staticmethod
    def parse(message):
        target = Target[message.get("target", "none")]

        if target is Target.game:
            return GameTargetMessage.build(message)
        elif target is Target.connectivity:
            return ConnectivityTargetMessage.build(message)
        else:
            return LobbyTargetMessage.parse(message)

    @staticmethod
    def parse_command(message):
        try:
            return CommandField[message.get("command")]
        except KeyError:
            raise MessageParsingError(
                f"'command' field of message {message} is invalid."
            )


class MessageParsingError(Exception):
    """Raised if trying to parse a message with invalid format."""

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
