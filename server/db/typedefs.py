# To prevent import issues, enums used by models should be defined in the db
# package

from enum import Enum, unique


@unique
class Victory(Enum):
    DEMORALIZATION = 0
    DOMINATION = 1
    ERADICATION = 2
    SANDBOX = 3


@unique
class GameOutcome(Enum):
    VICTORY = "VICTORY"
    DEFEAT = "DEFEAT"
    DRAW = "DRAW"
    UNKNOWN = "UNKNOWN"
