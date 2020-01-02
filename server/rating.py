from enum import Enum
from collections.abc import MutableMapping
from trueskill import Rating


# Values correspond to legacy table names. This will be fixed when db gets
# migrated.
class RatingType(Enum):
    GLOBAL = "global"
    LADDER_1V1 = "ladder1v1"


class RatingTypeMap(MutableMapping):
    def __init__(self, default):
        MutableMapping.__init__(self)
        self._back = {}

        for rtype in RatingType:
            self[rtype] = default

    def __getitem__(self, key: RatingType):
        return self._back[key]

    def __setitem__(self, key: RatingType, value):
        self._back[key] = value

    def __delitem__(self, key: RatingType):
        del self._back[key]

    def __iter__(self):
        return iter(self._back)

    def __len__(self):
        return len(self._back)


# Only used to coerce rating type.
class PlayerRatings(RatingTypeMap):
    def __setitem__(self, key: RatingType, value):
        if isinstance(value, Rating):
            val = (value.mu, value.sigma)
        else:
            val = value
        self._back[key] = val
