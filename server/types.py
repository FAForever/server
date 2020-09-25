from typing import NamedTuple, Optional


class GameLaunchOptions(NamedTuple):
    """Additional options used to configure the FA lobby"""

    mapname: Optional[str] = None
    team: Optional[int] = None
    faction: Optional[int] = None
    expected_players: Optional[int] = None
    map_position: Optional[int] = None


class Map(NamedTuple):
    id: int
    name: str
    path: str
