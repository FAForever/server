"""
General type definitions
"""

import base64
import random
from typing import Any, Dict, NamedTuple, Optional, Protocol


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
    game_options: Optional[Dict[str, Any]] = None


class MapPoolMap(Protocol):
    id: int
    weight: int

    def get_map(self) -> "Map": ...


class Map(NamedTuple):
    id: int
    name: str
    path: str
    weight: int = 1

    def get_map(self) -> "Map":
        return self


class NeroxisGeneratedMap(NamedTuple):
    id: int
    version: str
    spawns: int
    map_size_pixels: int
    weight: int = 1

    @classmethod
    def of(cls, params: dict, weight: int = 1):
        assert params["type"] == "neroxis"

        map_size_pixels = int(params["size"])

        if map_size_pixels <= 0:
            raise Exception("Map size is zero or negative")

        if map_size_pixels % 64 != 0:
            raise Exception("Map size is not a multiple of 64")

        spawns = int(params["spawns"])
        if spawns % 2 != 0:
            raise Exception("spawns is not a multiple of 2")

        version = params["version"]
        return NeroxisGeneratedMap(
            -int.from_bytes(bytes(f"{version}_{spawns}_{map_size_pixels}", encoding="ascii"), "big"),
            version,
            spawns,
            map_size_pixels,
            weight
        )

    def get_map(self) -> Map:
        """
        Generate a map name based on the version and parameters. If invalid
        parameters are specified hand back None
        """
        seed_bytes = random.getrandbits(64).to_bytes(8, "big")
        size_byte = (self.map_size_pixels // 64).to_bytes(1, "big")
        spawn_byte = self.spawns.to_bytes(1, "big")
        option_bytes = spawn_byte + size_byte
        seed_str = base64.b32encode(seed_bytes).decode("ascii").replace("=", "").lower()
        option_str = base64.b32encode(option_bytes).decode("ascii").replace("=", "").lower()
        map_name = f"neroxis_map_generator_{self.version}_{seed_str}_{option_str}"
        map_path = f"maps/{map_name}.zip"
        return Map(self.id, map_name, map_path, self.weight)
