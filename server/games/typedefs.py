from enum import Enum, unique
from typing import Any, NamedTuple, Optional

from server.db.typedefs import Victory
from server.games.game_results import ArmyResult, GameOutcome
from server.players import Player


@unique
class GameState(Enum):
    INITIALIZING = 0
    LOBBY = 1
    LIVE = 2
    ENDED = 3


@unique
class GameConnectionState(Enum):
    INITIALIZING = 0
    INITIALIZED = 1
    CONNECTED_TO_HOST = 2
    ENDED = 3


@unique
class GameType(Enum):
    COOP = "coop"
    CUSTOM = "custom"
    MATCHMAKER = "matchmaker"


@unique
class VisibilityState(Enum):
    PUBLIC = "public"
    FRIENDS = "friends"


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
    HOST_SET_UNRANKED = 25


class FeaturedModType():
    """
    String constants for featured mod technical_name
    """

    COOP = "coop"
    FAF = "faf"
    FAFBETA = "fafbeta"
    LADDER_1V1 = "ladder1v1"


class BasicGameInfo(NamedTuple):
    """
    Holds basic information about a game that does not change after launch.
    Fields:
     - game_id: id of the game
     - rating_type: str (e.g. "ladder1v1")
     - map_id: id of the map used
     - game_mode: name of the featured mod
    """

    game_id: int
    rating_type: Optional[str]
    map_id: int
    game_mode: str
    mods: list[int]
    teams: list[set[Player]]


class TeamRatingSummary(NamedTuple):
    outcome: GameOutcome
    player_ids: set[int]
    army_results: list[ArmyResult]


class EndedGameInfo(NamedTuple):
    """
    Holds the outcome of an ended game.
    Fields:
     - game_id: id of the game
     - rating_type: str (e.g. "ladder1v1")
     - map_id: id of the map used
     - game_mode: name of the featured mod
     - validity: ValidityState (e.g. VALID or TOO_SHORT)
     - team_summaries: a list of TeamRatingSummaries containing IDs of players
       on the team and the team's outcome
    """

    game_id: int
    rating_type: Optional[str]
    map_id: int
    game_mode: str
    mods: list[int]
    commander_kills: dict[str, int]
    validity: ValidityState
    team_summaries: list[TeamRatingSummary]

    @classmethod
    def from_basic(
        cls,
        basic_info: BasicGameInfo,
        validity: ValidityState,
        team_outcomes: list[GameOutcome],
        commander_kills: dict[str, int],
        team_army_results: list[list[ArmyResult]],
    ) -> "EndedGameInfo":
        if len(basic_info.teams) != len(team_outcomes):
            raise ValueError(
                "Team sets of basic_info and team outcomes must refer to the "
                "same number of teams in the same order."
            )

        return cls(
            basic_info.game_id,
            basic_info.rating_type,
            basic_info.map_id,
            basic_info.game_mode,
            basic_info.mods,
            commander_kills,
            validity,
            [
                TeamRatingSummary(outcome, set(player.id for player in team), army_results)
                for outcome, team, army_results
                in zip(team_outcomes, basic_info.teams, team_army_results)
            ],
        )

    def to_dict(self):
        return {
            "game_id": self.game_id,
            "rating_type": self.rating_type
            if self.rating_type is not None
            else "None",
            "map_id": self.map_id,
            "featured_mod": self.game_mode,
            "sim_mod_ids": self.mods,
            "commander_kills": self.commander_kills,
            "validity": self.validity.name,
            "teams": [
                {
                    "outcome": team_summary.outcome.name,
                    "player_ids": list(team_summary.player_ids),
                    "army_results": [result._asdict() for result in team_summary.army_results],
                }
                for team_summary in self.team_summaries
            ],
        }


class _FAEnabled(object):
    __slots__ = ()

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            other = other.lower()

        return other in (True, "true", "on", "yes", 1)


class _FADisabled(object):
    __slots__ = ()

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            other = other.lower()

        return other in (False, "false", "off", "no", 0)


class FA(object):
    __slots__ = ()

    ENABLED = _FAEnabled()
    DISABLED = _FADisabled()


__all__ = (
    "BasicGameInfo",
    "EndedGameInfo",
    "FA",
    "FeaturedModType",
    "GameConnectionState",
    "GameState",
    "GameType",
    "TeamRatingSummary",
    "ValidityState",
    "Victory",
    "VisibilityState",
)
