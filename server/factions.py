from enum import IntEnum, unique


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
        return Faction.__members__[value]
