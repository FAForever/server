from enum import IntEnum, unique


@unique
class Faction(IntEnum):
    uef = 1
    aeon = 2
    cybran = 3
    seraphim = 4
    nomad = 5

    @staticmethod
    def from_string(value):
        return getattr(Faction, value)
