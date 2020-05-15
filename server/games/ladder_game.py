import logging

from server.abc.base_game import InitMode
from server.players import Player
from server.rating import RatingType

from .game import Game, GameOutcome

logger = logging.getLogger(__name__)


class LadderGame(Game):
    """Class for 1v1 ladder games"""

    init_mode = InitMode.AUTO_LOBBY

    def __init__(self, id_, *args, **kwargs):
        new_kwargs = {
            "game_mode": "ladder1v1",
            "rating_type": RatingType.LADDER_1V1,
            "max_players": 2
        }
        new_kwargs.update(kwargs)
        super().__init__(id_, *args, **new_kwargs)

    def is_winner(self, player: Player):
        return self.get_player_outcome(player) is GameOutcome.VICTORY

    def get_army_score(self, army: int) -> int:
        """
        We override this function so that ladder game scores are only reported
        as 1 for win and 0 for anything else.
        """
        return self._results.victory_only_score(army)
