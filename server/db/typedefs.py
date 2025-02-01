# To prevent import issues, enums used by models should be defined in the db
# package

from enum import Enum, unique


@unique
class Victory(Enum):
    DEMORALIZATION = "DEMORALIZATION"
    DOMINATION = "DOMINATION"
    ERADICATION = "ERADICATION"
    SANDBOX = "SANDBOX"
    DECAPITATION = "DECAPITATION"


@unique
class GameOutcome(Enum):
    VICTORY = "VICTORY"
    DEFEAT = "DEFEAT"
    DRAW = "DRAW"
    UNKNOWN = "UNKNOWN"
