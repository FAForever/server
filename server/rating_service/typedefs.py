from typing import Dict, List, Set, NamedTuple

from server.games.game_results import GameOutcome
from server.rating import RatingType
from trueskill import Rating

PlayerID = int


class TeamRatingData(NamedTuple):
    outcome: GameOutcome
    ratings: Dict[int, Rating]


GameRatingData = List[TeamRatingData]


class TeamRatingSummary(NamedTuple):
    outcome: GameOutcome
    player_ids: Set[int]


class GameRatingSummary(NamedTuple):
    """
    Holds minimal information needed to rate a game.
    Fields:
     - game_id: id of the game to rate
     - rating_type: RatingType to (e.g. LADDER_1V1)
     - results: a list of dictionaries mapping player ids to their `GameOutcome`s
     - teams: a tuple of two TeamRatingSummaries
    Every dictionary in the results list should correspond to a distinct team.
    """

    game_id: int
    rating_type: RatingType
    teams: List[TeamRatingSummary]


class RatingServiceError(Exception):
    pass


class ServiceNotReadyError(RatingServiceError):
    pass
