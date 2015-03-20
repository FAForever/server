from abc import ABCMeta, abstractmethod
from enum import Enum
from src.players import Player


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

    @abstractmethod
    def rate_game(self):
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
