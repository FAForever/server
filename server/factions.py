from enum import IntEnum, unique
from typing import Union


@unique
class Faction(IntEnum):
    uef = 1
    aeon = 2
    cybran = 3
    seraphim = 4
    # This is not entirely accurate as 5 can also represent "random" in which
    # case nomad has value 6
    nomad = 5

    @staticmethod
    def from_string(value: str) -> "Faction":
        return Faction.__members__[value.lower()]

    @staticmethod
    def from_value(value: Union[str, int]) -> "Faction":
        if isinstance(value, str):
            return Faction.from_string(value)
        elif isinstance(value, int):
            return Faction(value)

        raise TypeError(f"Unsupported faction type {type(value)}!")
