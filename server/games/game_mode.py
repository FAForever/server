from enum import Enum


class GameMode(Enum):
    UNKNOWN = None
    LADDER = "ladder1v1"
    COOP = "coop"
    FAF = "faf"
    FAF_BETA = "fafbeta"
    EQUILIBRIUM = "equilibrium"

    @staticmethod
    def from_string(string: str) -> "GameMode":
        return {
            "ladder1v1": GameMode.LADDER,
            "coop": GameMode.COOP,
            "faf": GameMode.FAF,
            "fafbeta": GameMode.FAF_BETA,
            "equilibrium": GameMode.EQUILIBRIUM,
        }.get(string, GameMode.UNKNOWN)

    def __str__(self):
        return str(self.value)
