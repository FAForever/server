from typing import Dict, List

import trueskill

from server.config import config
from server.games.game_results import GameOutcome
from server.rating import Rating
from server.rating_service.typedefs import GameRatingSummary

from ..decorators import with_logger
from .typedefs import PlayerID, RatingDict


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
        self.ranks = _ranks_from_team_outcomes(self.team_outcomes)

    def compute_rating(
        self,
        ratings: RatingDict
    ) -> RatingDict:
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

    def get_outcome_map(self) -> Dict[PlayerID, GameOutcome]:
        return self.outcome_map


@with_logger
class AdjustmentGameRater(GameRater):
    """GameRater for performing adjustments using another GameRater"""

    def __init__(self, rater: GameRater, base_ratings: RatingDict):
        self.rater = rater
        self.base_ratings = base_ratings

    def compute_rating(
        self,
        ratings: RatingDict
    ) -> RatingDict:
        """
        Adjust one rating to bring it closer to a different base rating. For
        each player, this will rate the game with trueskill as if they
        played this game with the rating we are adjusting instead of the
        base rating. Adjustments are only returned under certain conditions to
        prevent rating manipulation.
        """
        new_adjusted_ratings = {}
        for player_id, base_rating in self.base_ratings.items():
            old_adjusted_rating = ratings[player_id]
            # Since we only adjust upwards, we should not adjust ratings that
            # are already higher than the base.
            if base_rating.displayed() < old_adjusted_rating.displayed():
                continue
            # Make a copy of the base ratings, but substitute this player's
            # rating with the rating we are adjusting.
            old_ratings = dict(self.base_ratings)
            old_ratings[player_id] = old_adjusted_rating

            new_ratings = self.rater.compute_rating(old_ratings)
            new_adjusted_rating = new_ratings[player_id]
            self._logger.debug(
                "Got new adjusted rating for player %d: %s",
                player_id,
                new_adjusted_rating
            )
            if (
                old_adjusted_rating.displayed() <
                new_adjusted_rating.displayed() <=
                config.RATING_ADJUSTMENT_MAX_RATING
            ):
                new_adjusted_ratings[player_id] = new_adjusted_rating

        return new_adjusted_ratings

    def get_outcome_map(self) -> Dict[PlayerID, GameOutcome]:
        return self.rater.outcome_map


def _ranks_from_team_outcomes(outcomes: List[GameOutcome]) -> List[int]:
    if outcomes == [GameOutcome.DRAW, GameOutcome.DRAW]:
        return [0, 0]
    elif outcomes == [GameOutcome.VICTORY, GameOutcome.DEFEAT]:
        return [0, 1]
    elif outcomes == [GameOutcome.DEFEAT, GameOutcome.VICTORY]:
        return [1, 0]
    else:
        raise GameRatingError(f"Inconsistent outcomes {outcomes}")
