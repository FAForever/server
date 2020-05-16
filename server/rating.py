from enum import Enum
from typing import DefaultDict, Tuple, TypeVar, Union

from trueskill import Rating


# Values correspond to legacy table names. This will be fixed when db gets
# migrated.
class RatingType(Enum):
    GLOBAL = "global"
    LADDER_1V1 = "ladder_1v1"

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        else:
            return super().__eq__(other)

    def __hash__(self):
        return hash(self.value)


K = Union[RatingType, str]
V = TypeVar("V")


class RatingTypeMap(DefaultDict[K, V]):
    """
    A thin wrapper around `defaultdict` which stores RatingType keys as strings.
    """
    def __init__(self, default_factory, *args, **kwargs):
        super().__init__(default_factory, *args, **kwargs)

        # Initialize defaults for enumerated rating types
        for rating in RatingType:
            self[rating]

    def __setitem__(self, key: K, value: V) -> None:
        if isinstance(key, RatingType):
            new_key = key.value
        else:
            new_key = key
        super().__setitem__(new_key, value)


# Only used to coerce rating type.
class PlayerRatings(RatingTypeMap[Tuple[float, float]]):
    def __setitem__(self, key: K, value: Tuple[float, float]):
        if isinstance(value, Rating):
            val = (value.mu, value.sigma)
        else:
            val = value
        super().__setitem__(key, val)
