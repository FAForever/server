from copy import deepcopy
import time

from .game import Game, ValidityState
from server.abc.base_game import InitMode
from server.decorators import with_logger

@with_logger
class CustomGame(Game):
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, id, parent):
        super(self.__class__, self).__init__(id, parent)
  
    def rate_game(self):
        limit = len(self.players) * 60
        if time.time() - self.launched_at < limit:
            self.mark_invalid(ValidityState.TOO_SHORT)
        if self.validity == ValidityState.VALID:
            new_ratings = self.compute_rating()
            self.persist_rating_change_stats(new_ratings, rating='global')
