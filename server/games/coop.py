
from server.abc.base_game import InitMode
from . import GamesContainer
from .game import Game
class CoopGame(Game):
    """Class forcoop game"""

    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, uuid, parent = None):
        super(self.__class__, self).__init__(uuid, parent)



class CoopGamesContainer(GamesContainer):
    """Class for coop games"""
    listable = False

    def __init__(self, db, games_service=None, name='coop', nice_name='coop'):
        super(CoopGamesContainer, self).__init__(name, nice_name, db, games_service)

        self.host = False
        self.join = False
