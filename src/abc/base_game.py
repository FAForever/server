from abc import ABCMeta, abstractmethod, abstractproperty
from enum import Enum, IntEnum
from src.players import Player


class GameConnectionState(Enum):
    INITIALIZING = 0
    INITIALIZED = 1
    CONNECTED_TO_HOST = 2
    ENDED = 3
    ABORTED = 4


class InitMode(IntEnum):
    NORMAL_LOBBY = 0
    AUTO_LOBBY = 1


class BaseGame():
    __metaclass__ = ABCMeta

    @abstractmethod
    def on_game_end(self):
        pass  # pragma: no cover

    def rate_game(self):
        pass  # pragma: no cover

    @property
    @abstractmethod
    def init_mode(self):
        """
        The intialization mode to use for the Game
        :rtype InitMode
        :return:
        """
        pass  # pragma: no cover

    @abstractmethod
    def teams(self):
        """
        A dictionary of lists representing teams

        It is of the form:
        >>> {
        >>>     1: [Player(1), Player(2)],
        >>>     2: [Player(3), Player(4)]
        >>> }
        :return:
        """
        pass  # pragma: no cover
