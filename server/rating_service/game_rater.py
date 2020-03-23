from typing import Dict, List, Tuple, Set

import trueskill
from server.games.game_results import GameOutcome
from trueskill import Rating

from ..decorators import with_logger

from .typedefs import (
    PlayerID,
    RatingGroups,
    GameRatingData,
    RatingData,
)


class GameRatingError(Exception):
    pass


@with_logger
class GameRater:
    @classmethod
    def compute_rating(
        cls, rating_data: GameRatingData
    ) -> Tuple[Dict[PlayerID, Rating], Dict[PlayerID, GameOutcome]]:
        rating_groups = [
            {player_id: data.rating for player_id, data in team.items()}
            for team in rating_data
        ]
        cls._check_rating_groups(rating_groups)

        team_outcomes = [
            set(player.outcome for player in team.values()) for team in rating_data
        ]
        ranks = cls._ranks_from_team_outcomes(team_outcomes)

        cls._logger.debug("Rating groups: %s", rating_groups)
        cls._logger.debug("Ranks: %s", ranks)

        new_rating_groups = trueskill.rate(rating_groups, ranks)

        player_rating_map = {
            player_id: new_rating
            for team in new_rating_groups
            for player_id, new_rating in team.items()
        }

        clean_team_outcomes = cls._ranks_to_clean_outcomes(ranks)
        player_outcome_map = {
            player_id: clean_team_outcomes[team_index]
            for team_index, team in enumerate(rating_groups)
            for player_id in team
        }

        return player_rating_map, player_outcome_map

    @staticmethod
    def _check_rating_groups(rating_groups: RatingGroups):
        if len(rating_groups) != 2:
            raise GameRatingError(
                "Attempted to rate game with other than two parties. "
                f"Rating groups: {rating_groups}"
            )

    @staticmethod
    def _ranks_from_team_outcomes(team_outcomes: List[Set[GameOutcome]]) -> List[int]:
        """
        Takes a list of length two containing sets of GameOutcomes
        for individual players on a team
        and converts into rank representation for trueskill.
        Throws GameRatingError if outcomes are inconsistent or ambiguous.
        :param team_outcomes: list of GameOutcomes
        :return: list of ranks as to be used with trueskill
        """
        victory0 = GameOutcome.VICTORY in team_outcomes[0]
        victory1 = GameOutcome.VICTORY in team_outcomes[1]
        both_claim_victory = victory0 and victory1
        someone_claims_victory = victory0 or victory1
        if both_claim_victory:
            raise GameRatingError(
                "Attempted to rate game in which both teams claimed victory. "
                f" Team outcomes: {team_outcomes}"
            )
        elif someone_claims_victory:
            return [
                0 if GameOutcome.VICTORY in outcomes else 1
                for outcomes in team_outcomes
            ]

        # Now know that no-one has GameOutcome.VICTORY
        draw0 = (
            GameOutcome.DRAW in team_outcomes[0]
            or GameOutcome.MUTUAL_DRAW in team_outcomes[0]
        )
        draw1 = (
            GameOutcome.DRAW in team_outcomes[1]
            or GameOutcome.MUTUAL_DRAW in team_outcomes[1]
        )
        both_claim_draw = draw0 and draw1
        someone_claims_draw = draw0 or draw1
        if both_claim_draw:
            return [0, 0]
        elif someone_claims_draw:
            raise GameRatingError(
                "Attempted to rate game with unilateral draw. "
                f" Team outcomes: {team_outcomes}"
            )

        # Now know that the only results are DEFEAT or UNKNOWN/CONFLICTING
        # Unrank if there are any players with unknown result
        all_outcomes = team_outcomes[0] | team_outcomes[1]
        if (
            GameOutcome.UNKNOWN in all_outcomes
            or GameOutcome.CONFLICTING in all_outcomes
        ):
            raise GameRatingError(
                "Attempted to rate game with ambiguous outcome. "
                f" Team outcomes: {team_outcomes}"
            )

        # Otherwise everyone is DEFEAT, we return a draw
        return [0, 0]

    @staticmethod
    def _ranks_to_clean_outcomes(ranks: List[int]) -> List[GameOutcome]:
        if ranks == [0, 0]:
            return [GameOutcome.DRAW, GameOutcome.DRAW]
        elif ranks == [1, 0]:
            return [GameOutcome.DEFEAT, GameOutcome.VICTORY]
        elif ranks == [0, 1]:
            return [GameOutcome.VICTORY, GameOutcome.DEFEAT]
        else:
            raise GameRatingError(f"Inconsistent ranks {ranks}")
