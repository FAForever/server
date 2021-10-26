from typing import Dict, List

import trueskill

from server.games.game_results import GameOutcome
from server.rating import Rating
from server.rating_service.typedefs import GameRatingSummary

from ..decorators import with_logger
from .typedefs import PlayerID


class GameRatingError(Exception):
    pass


@with_logger
class GameRater:
    def __init__(self, summary: GameRatingSummary):
        self.summary = summary
        self.outcome_map = {
            player_id: team.outcome
            for team in summary.teams
            for player_id in team.player_ids
        }
        self.player_ids = list(self.outcome_map.keys())
        self.team_outcomes = [team.outcome for team in summary.teams]
        self.ranks = self._ranks_from_team_outcomes(self.team_outcomes)

    def compute_rating(
        self,
        ratings: Dict[PlayerID, Rating]
    ) -> Dict[PlayerID, Rating]:
        rating_groups = [
            {
                player_id: trueskill.Rating(*ratings[player_id])
                for player_id in team.player_ids
            }
            for team in self.summary.teams
        ]

        self._logger.debug("Rating groups: %s", rating_groups)
        self._logger.debug("Ranks: %s", self.ranks)

        new_rating_groups = trueskill.rate(rating_groups, self.ranks)

        player_rating_map = {
            player_id: Rating(*new_rating)
            for team in new_rating_groups
            for player_id, new_rating in team.items()
        }

        return player_rating_map

    @staticmethod
    def _ranks_from_team_outcomes(outcomes: List[GameOutcome]) -> List[int]:
        if outcomes == [GameOutcome.DRAW, GameOutcome.DRAW]:
            return [0, 0]
        elif outcomes == [GameOutcome.VICTORY, GameOutcome.DEFEAT]:
            return [0, 1]
        elif outcomes == [GameOutcome.DEFEAT, GameOutcome.VICTORY]:
            return [1, 0]
        else:
            raise GameRatingError(f"Inconsistent outcomes {outcomes}")
