from enum import Enum


class GameConnectionState(Enum):
    initializing = 0
    initialized = 1
    connected_to_host = 2
    ended = 3
    aborted = 4