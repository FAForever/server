import logging

from server.abc.base_game import InitMode
from server.players import Player

from .game import Game, GameOutcome, ValidityState
from server.rating import RatingType

logger = logging.getLogger(__name__)


class LadderGame(Game):
    """Class for 1v1 ladder games"""
    init_mode = InitMode.AUTO_LOBBY

    def __init__(self, id_, *args, **kwargs):
        super(self.__class__, self).__init__(id_, *args, **kwargs)
        self.game_mode = 'ladder1v1'
        self.max_players = 2

    async def rate_game(self):
        if self.validity == ValidityState.VALID:
            new_ratings = self.compute_rating(RatingType.LADDER_1V1)
            await self.persist_rating_change_stats(new_ratings, RatingType.LADDER_1V1)

    def is_winner(self, player: Player):
        return self.outcome(player) is GameOutcome.VICTORY

    def get_army_score(self, army: int) -> int:
        """
        We override this function so that ladder game scores are only reported
        as 1 for win and 0 for anything else.
        """
        return self._results.victory_only_score(army)
