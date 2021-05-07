from typing import Any, NamedTuple, Optional

from server.factions import Faction
from server.matchmaker import MatchmakerQueue
from server.players import Player
from server.types import Map


class MQMatchmakingRequest(NamedTuple):
    game_name: str
    map: Map
    featured_mod: str
    participants: list["MQMatchmakingRequestParticipant"]
    game_options: dict[str, Any]
    queue: Optional[MatchmakerQueue]


class MQMatchmakingRequestParticipant(NamedTuple):
    player: Player
    faction: Faction
    team: int
    slot: int
