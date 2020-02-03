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


class Message():
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

class CoopListMessage(LobbyTargetMessage):
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

        return cls(
            "social_remove",
            id_to_remove,
        )


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

        return cls(
            "social_add",
            id_to_add,
            adding_a_friend,
        )


class BottleneckMessage(LobbyTargetMessage):
    """
    Not yet implemented
    """

    def __init__(self, lobbyconnection=None, message=None):
        raise NotImplementedError


class AdminMessage(LobbyTargetMessage):
    """
    Not yet implemented
    """

    def __init__(self, lobbyconnection=None, message=None):
        raise NotImplementedError


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
        mod = str(message.get("mod", "ladder1v1")),

        if str(message.get("state")) not in ["start", "stop"]:
            raise MessageParsingError(
                f"Message with command 'game_matchmaking' "
                f"must contain the field 'state' set to 'start' or 'stop'. "
                f"Offending message: {message}."
            )
        state = str(message["state"])

        return cls(
            "game_matchmaking",
            mod,
            state,
        )


class GameHostMessage(LobbyTargetMessage):
    """
    Not yet implemented
    """

    def __init__(self, lobbyconnection=None, message=None):
        raise NotImplementedError


class GameJoinMessage(LobbyTargetMessage):
    """
    Not yet implemented
    """

    def __init__(self, lobbyconnection=None, message=None):
        raise NotImplementedError


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

        return cls(
            "avatar",
            action,
            avatar_url,
        )


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
