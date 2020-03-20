from typing import Dict, Iterable, List

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
        rating_type=RatingType.GLOBAL
    ):
        self._rating_type = rating_type
        self._outcome_by_player = outcome_by_player
        self._players_by_team = players_by_team

    def compute_rating(self) -> Dict[Player, Rating]:
        rating_groups = self._get_rating_groups()
        team_outcomes = [
            self._get_team_outcome(team.keys()) for team in rating_groups
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
                len(self._players_by_team[FFA_TEAM]) +
                len(self._players_by_team) - 1
            )
            if (
                len(self._players_by_team[FFA_TEAM]) == 2
                and len(self._players_by_team) == 1
            ):
                return [{
                    player: Rating(*player.ratings[self._rating_type])
                } for player in self._players_by_team[FFA_TEAM]]
            elif number_of_parties != 2:
                raise GameRatingError(
                    f"Attempted to rate FFA game with other than two parties: {{team: players}} = {self._players_by_team}"
                )

        if len(self._players_by_team) == 2:
            return [{
                player: Rating(*player.ratings[self._rating_type])
                for player in team
            } for _, team in self._players_by_team.items()]
        else:
            raise GameRatingError(
                f"Attempted to rate non-FFA game with other than two teams: {{team: players}} = {self._players_by_team}"
            )

    def _get_team_outcome(self, team: Iterable[Player]) -> GameOutcome:
        outcomes = set(self._outcome_by_player[player] for player in team)
        outcomes.discard(GameOutcome.UNKNOWN)

        # Treat conflicting reports as unknown
        # to make it harder to unrank games by faking reports
        outcomes.discard(GameOutcome.CONFLICTING)

        if not outcomes:
            return GameOutcome.UNKNOWN
        if GameOutcome.VICTORY in outcomes:
            # One player surviving implies that the entire team won
            return GameOutcome.VICTORY
        if len(outcomes) > 1:
            raise GameRatingError(
                f"Attempted to rate game where one of the teams has inconsistent outcome. Teams: {self._players_by_team} Outcomes: {self._outcome_by_player}"
            )
        else:
            return outcomes.pop()

    def _ranks_from_team_outcomes(self, team_outcomes: List[GameOutcome]
                                  ) -> List[int]:
        """
        Takes a list of length two containing the GameOutcomes and converts into rank representation for trueskill
        If any of the GameOutcomes are UNKNOWN, they are assumed to be VICTORY, DEFEAT, or DRAW, whichever is consistent with the other reported outcome.
        Throws GameRatingError if both outcomes are UNKNOWN
        :param team_outcomes: list of GameOutcomes
        :return: list of ranks as to be used with trueskill
        """
        both_unknown = team_outcomes == [
            GameOutcome.UNKNOWN, GameOutcome.UNKNOWN
        ]
        at_most_one_win = team_outcomes.count(GameOutcome.VICTORY) < 2
        at_most_one_defeat = team_outcomes.count(GameOutcome.DEFEAT) < 2
        no_draw = not (
            GameOutcome.DRAW in team_outcomes
            or GameOutcome.MUTUAL_DRAW in team_outcomes
        )
        both_draw = set(team_outcomes) < {
            GameOutcome.DRAW, GameOutcome.MUTUAL_DRAW
        }
        both_defeat = team_outcomes == [GameOutcome.DEFEAT, GameOutcome.DEFEAT]

        if both_unknown:
            raise GameRatingError(
                f"Attempted to rate game with unknown outcome. Teams: {self._players_by_team} Outcomes: {self._outcome_by_player}"
            )
        elif no_draw and at_most_one_defeat and at_most_one_win:
            if GameOutcome.VICTORY in team_outcomes:
                return [
                    0 if x is GameOutcome.VICTORY else 1 for x in team_outcomes
                ]
            else:
                return [
                    1 if x is GameOutcome.DEFEAT else 0 for x in team_outcomes
                ]
        elif both_draw or both_defeat:
            return [0, 0]
        else:
            raise GameRatingError(
                f"Attempted to rate game with inconsistent outcome. Teams: {self._players_by_team} Outcomes by player: {self._outcome_by_player} Outcomes by team: {team_outcomes}"
            )
