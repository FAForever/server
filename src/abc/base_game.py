from abc import ABCMeta, abstractmethod
from enum import Enum


class GameConnectionState(Enum):
    initializing = 0
    initialized = 1
    connected_to_host = 2
    ended = 3
    aborted = 4


class BaseGame():
    __metaclass__ = ABCMeta

    @abstractmethod
    def on_game_end(self):
        pass  # pragma: no cover
