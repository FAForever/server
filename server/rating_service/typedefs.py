from typing import Dict, List, NamedTuple, Optional

from server.games.game_results import GameOutcome
from server.rating import RatingType
from trueskill import Rating

PlayerID = int
SummaryResults = List[Dict[PlayerID, GameOutcome]]
RatingGroups = List[Dict[PlayerID, Rating]]


class RatingData(NamedTuple):
    outcome: GameOutcome
    rating: Rating


GameRatingData = List[Dict[PlayerID, RatingData]]


class GameRatingSummary(NamedTuple):
    """
    Holds minimal information needed to rate a game.
    Fields:
     - game_id: id of the game to rate
     - rating_type: RatingType to (e.g. LADDER_1V1)
     - results: a list of dictionaries mapping player ids to their `GameOutcome`s
    Every dictionary in the results list should correspond to a distinct team.
    """

    game_id: int
    rating_type: Optional[RatingType]
    results: SummaryResults


class RatingServiceError(Exception):
    pass


class ServiceNotReadyError(RatingServiceError):
    pass


class RatingNotFoundError(RatingServiceError):
    pass
