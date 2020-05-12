from typing import NamedTuple, Optional


class Address(NamedTuple):
    """A peer IP address"""

    host: str
    port: int

    @classmethod
    def from_string(cls, address: str) -> "Address":
        host, port = address.rsplit(":", 1)
        return cls(host, int(port))


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
