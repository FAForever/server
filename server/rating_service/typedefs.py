from typing import Dict, List, NamedTuple

from server.games.game_results import GameOutcome
from server.games.typedefs import TeamRatingSummary

PlayerID = int


class Rating(NamedTuple):
    """
    A dumb container for holding a mean, deviation pair in a single container.
    Uses mean, dev to differentiate from the trueskill.Rating type.
    """
    mean: float
    dev: float

    def displayed(self) -> float:
        return self.mean - 3 * self.dev


class GameRatingSummary(NamedTuple):
    """
    Holds minimal information needed to rate a game.
    Fields:
     - game_id: id of the game to rate
     - rating_type: str (e.g. "ladder1v1")
     - teams: a list of two TeamRatingSummaries
    """

    game_id: int
    rating_type: str
    teams: List[TeamRatingSummary]

    @classmethod
    def from_game_info_dict(cls, game_info: Dict) -> "GameRatingSummary":
        if len(game_info["teams"]) != 2:
            raise ValueError("Detected other than two teams.")

        return cls(
            game_info["game_id"],
            game_info["rating_type"],
            [
                TeamRatingSummary(
                    GameOutcome(summary["outcome"]),
                    set(summary["player_ids"]),
                    summary["army_results"],
                )
                for summary in game_info["teams"]
            ],
        )


class RatingServiceError(Exception):
    pass


class ServiceNotReadyError(RatingServiceError):
    pass
