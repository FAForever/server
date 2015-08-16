from server.abc.base_game import InitMode
from . import GamesContainer
from .game import Game, ValidityState


class CoopGame(Game):
    """Class forcoop game"""
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, id, parent = None):
        super(self.__class__, self).__init__(id, parent)

        self.validity = ValidityState.COOP_NOT_RANKED

class CoopGamesContainer(GamesContainer):
    """Class for coop games"""
    listable = False

    def __init__(self, db, desc, games_service=None,  name='coop', nice_name='coop'):
        super(CoopGamesContainer, self).__init__(name, desc, nice_name, db, games_service)
