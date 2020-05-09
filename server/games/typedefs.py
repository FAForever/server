from enum import Enum, unique
from typing import Dict, NamedTuple, Optional

from server.games.game_results import GameOutcome
from server.rating import RatingType


@unique
class GameState(Enum):
    INITIALIZING = 0
    LOBBY = 1
    LIVE = 2
    ENDED = 3


@unique
class Victory(Enum):
    DEMORALIZATION = 0
    DOMINATION = 1
    ERADICATION = 2
    SANDBOX = 3

    @staticmethod
    def from_gpgnet_string(value: str) -> Optional["Victory"]:
        """
        :param value: The string to convert from

        :return: Victory or None if the string is not valid
        """
        return {
            "demoralization": Victory.DEMORALIZATION,
            "domination": Victory.DOMINATION,
            "eradication": Victory.ERADICATION,
            "sandbox": Victory.SANDBOX,
        }.get(value)


@unique
class VisibilityState(Enum):
    PUBLIC = 0
    FRIENDS = 1

    @staticmethod
    def from_string(value: str) -> Optional["VisibilityState"]:
        """
        :param value: The string to convert from

        :return: VisibilityState or None if the string is not valid
        """
        return {
            "public": VisibilityState.PUBLIC,
            "friends": VisibilityState.FRIENDS,
        }.get(value)

    def to_string(self) -> Optional[str]:
        return {
            VisibilityState.PUBLIC: "public",
            VisibilityState.FRIENDS: "friends",
        }.get(self)


# Identifiers must be kept in sync with the contents of the invalid_game_reasons table.
# New reasons added should have a description added to that table. Identifiers should never be
# reused, and values should never be deleted from invalid_game_reasons.
@unique
class ValidityState(Enum):
    VALID = 0
    TOO_MANY_DESYNCS = 1
    WRONG_VICTORY_CONDITION = 2
    NO_FOG_OF_WAR = 3
    CHEATS_ENABLED = 4
    PREBUILT_ENABLED = 5
    NORUSH_ENABLED = 6
    BAD_UNIT_RESTRICTIONS = 7
    BAD_MAP = 8
    TOO_SHORT = 9
    BAD_MOD = 10
    COOP_NOT_RANKED = 11
    MUTUAL_DRAW = 12
    SINGLE_PLAYER = 13
    FFA_NOT_RANKED = 14
    UNEVEN_TEAMS_NOT_RANKED = 15
    UNKNOWN_RESULT = 16
    UNLOCKED_TEAMS = 17
    MULTI_TEAM = 18
    HAS_AI_PLAYERS = 19
    CIVILIANS_REVEALED = 20
    WRONG_DIFFICULTY = 21
    EXPANSION_DISABLED = 22
    SPAWN_NOT_FIXED = 23
    OTHER_UNRANK = 24


class BasicGameInfo(NamedTuple):
    """
    Holds basic information about a game that does not change after launch.
    Fields:
     - game_id: id of the game
     - rating_type: RatingType (e.g. LADDER_1V1)
     - teams: a dictionary mapping player IDs to their team IDs
    """

    game_id: int
    rating_type: RatingType
    map_id: int
    game_mode: str
    team_assignments: Dict[int, int]

    def to_dict(self):
        return {
            "game_id": self.game_id,
            "rating_type": self.rating_type.name,
            "map_id": self.map_id,
            "featured_mod": self.game_mode,
            "teams": self.team_assignments,
        }


class EndedGameInfo(NamedTuple):
    """
    Holds the outcome of an ended game.
    Fields:
     - game: BasicGameInfo with static information
     - validity: ValidityState (e.g. VALID or TOO_SHORT)
     - outcomes: a dictionary mapping player IDs to the resolved outcome of
       their team
    """

    game: BasicGameInfo
    validity: ValidityState
    outcomes: Dict[int, GameOutcome]

    def to_dict(self):
        base = self.game.to_dict()
        base.update(
            {
                "validity": self.validity.name,
                "outcomes": {
                    player_id: outcome.name
                    for player_id, outcome in self.outcomes.items()
                },
            }
        )
        return base
