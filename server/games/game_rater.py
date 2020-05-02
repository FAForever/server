from typing import Dict, List, Set

import trueskill
from server.config import FFA_TEAM
from server.games.game_results import GameOutcome
from server.players import Player
from server.rating import RatingType
from trueskill import Rating

from ..decorators import with_logger


class GameRatingError(Exception):
    pass


@with_logger
class GameRater(object):
    def __init__(
        self,
        players_by_team: Dict[int, List[Player]],
        outcome_by_player: Dict[Player, GameOutcome],
        rating_type=RatingType.GLOBAL,
    ):
        self._rating_type = rating_type
        self._outcome_by_player = outcome_by_player
        self._players_by_team = players_by_team

    def compute_rating(self) -> Dict[Player, Rating]:
        rating_groups = self._get_rating_groups()
        team_outcomes = [
            set(self._outcome_by_player[player] for player in team)
            for team in rating_groups
        ]
        ranks = self._ranks_from_team_outcomes(team_outcomes)

        self._logger.debug("Rating groups: %s", rating_groups)
        self._logger.debug("Ranks: %s", ranks)
        return trueskill.rate(rating_groups, ranks)

    def _get_rating_groups(self) -> List[Dict[Player, Rating]]:
        """
        Converts a dictionary mapping team ids to players to the trueskill rating_group format
        example input: {team1: [p1, p2], team2: [p3, p4]}
        example output: [ {p1: Rating, p2: Rating}, {p3: Rating, p4: Rating} ]
        """
        if FFA_TEAM in self._players_by_team:
            number_of_parties = (
                len(self._players_by_team[FFA_TEAM]) + len(self._players_by_team) - 1
            )
            if (
                len(self._players_by_team[FFA_TEAM]) == 2
                and len(self._players_by_team) == 1
            ):
                return [
                    {player: Rating(*player.ratings[self._rating_type])}
                    for player in self._players_by_team[FFA_TEAM]
                ]
            elif number_of_parties != 2:
                raise GameRatingError(
                    f"Attempted to rate FFA game with other than two parties: {{team: players}} = {self._players_by_team}"
                )

        if len(self._players_by_team) == 2:
            return [
                {player: Rating(*player.ratings[self._rating_type]) for player in team}
                for _, team in self._players_by_team.items()
            ]
        else:
            raise GameRatingError(
                f"Attempted to rate non-FFA game with other than two teams: {{team: players}} = {self._players_by_team}"
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
