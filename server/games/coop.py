from server.abc.base_game import InitMode
from .game import Game, ValidityState

class CoopGame(Game):
    """Class for coop game"""
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, id, parent = None):
        super(self.__class__, self).__init__(id, parent)

        self.validity = ValidityState.COOP_NOT_RANKED
