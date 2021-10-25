from typing import Dict, List

import trueskill

from server.games.game_results import GameOutcome
from server.games.typedefs import TeamRatingSummary

from ..decorators import with_logger
from .typedefs import PlayerID, Rating


class GameRatingError(Exception):
    pass


@with_logger
class GameRater:
    @classmethod
    def compute_rating(
        cls,
        teams: List[TeamRatingSummary],
        ratings: Dict[PlayerID, Rating]
    ) -> Dict[PlayerID, Rating]:
        rating_groups = [
            {
                player_id: trueskill.Rating(*ratings[player_id])
                for player_id in team.player_ids
            }
            for team in teams
        ]
        team_outcomes = [team.outcome for team in teams]
        ranks = cls._ranks_from_team_outcomes(team_outcomes)

        cls._logger.debug("Rating groups: %s", rating_groups)
        cls._logger.debug("Ranks: %s", ranks)

        new_rating_groups = trueskill.rate(rating_groups, ranks)

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
