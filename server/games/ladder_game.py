import logging
from typing import Optional

from server.config import config
from server.players import Player
from server.rating import RatingType

from .game import Game
from .game_results import ArmyOutcome, GameOutcome
from .typedefs import FeaturedModType, GameType

logger = logging.getLogger(__name__)


class LadderGame(Game):
    """Class for 1v1 ladder games"""
    game_type = GameType.MATCHMAKER

    def __init__(self, id_, *args, **kwargs):
        new_kwargs = {
            "game_mode": FeaturedModType.LADDER_1V1,
            "rating_type": RatingType.LADDER_1V1,
            "max_players": 2,
        }
        new_kwargs.update(kwargs)
        super().__init__(id_, *args, **new_kwargs)

    def is_winner(self, player: Player) -> bool:
        return self.get_player_outcome(player) is ArmyOutcome.VICTORY

    def get_army_score(self, army: int) -> int:
        """
        We override this function so that ladder game scores are only reported
        as 1 for win and 0 for anything else.
        """
        return self._results.victory_only_score(army)

    def _outcome_override_hook(self) -> Optional[list[GameOutcome]]:
        if not config.LADDER_1V1_OUTCOME_OVERRIDE or len(self.players) > 2:
            return None
        team_sets = self.get_team_sets()
        army_scores = [
            self._results.score(self.get_player_option(team_set.pop().id, "Army"))
            for team_set in team_sets
        ]
        if army_scores[0] > army_scores[1]:
            return [GameOutcome.VICTORY, GameOutcome.DEFEAT]
        elif army_scores[0] < army_scores[1]:
            return [GameOutcome.DEFEAT, GameOutcome.VICTORY]
        else:
            return [GameOutcome.DRAW, GameOutcome.DRAW]
