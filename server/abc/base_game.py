from enum import Enum, IntEnum, unique


@unique
class GameConnectionState(Enum):
    INITIALIZING = 0
    INITIALIZED = 1
    CONNECTED_TO_HOST = 2
    ENDED = 3


@unique
class InitMode(IntEnum):
    NORMAL_LOBBY = 0
    AUTO_LOBBY = 1
