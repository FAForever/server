from enum import Enum, unique

@unique
class Faction(Enum):
    uef = 1
    aeon = 2
    cybran = 3
    seraphim = 4
    nomads = 5

    @staticmethod
    def from_string(value):
        return getattr(Faction, value)
