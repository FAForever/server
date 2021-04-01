from typing import DefaultDict, Optional, Tuple, TypeVar, Union

from trueskill import Rating


# Values correspond to legacy table names. This will be fixed when db gets
# migrated.
class RatingType():
    GLOBAL = "global"
    LADDER_1V1 = "ladder_1v1"
    TMM_2V2 = "tmm_2v2"


K = Union[RatingType, str]
V = TypeVar("V")


class RatingTypeMap(DefaultDict[K, V]):
    """
    A thin wrapper around `defaultdict` which stores RatingType keys as strings.
    """
    def __init__(self, default_factory, *args, **kwargs):
        super().__init__(default_factory, *args, **kwargs)

        # Initialize defaults for enumerated rating types
        for rating in (RatingType.GLOBAL, RatingType.LADDER_1V1):
            self.__getitem__(rating)


# Only used to coerce rating type.
class PlayerRatings(RatingTypeMap[Tuple[float, float]]):
    def __setitem__(self, key: K, value: Tuple[float, float]) -> None:
        if isinstance(value, Rating):
            val = (value.mu, value.sigma)
        else:
            val = value
        super().__setitem__(key, val)

    def __getitem__(self, key: K) -> Tuple[float, float]:
        # TODO: Generalize for arbitrary ratings
        # https://github.com/FAForever/server/issues/727
        if key == RatingType.TMM_2V2 and key not in self:
            mean, dev = self[RatingType.GLOBAL]
            if dev > 250:
                tmm_2v2_rating = (mean, dev)
            else:
                tmm_2v2_rating = (mean, min(dev + 150, 250))

            self[key] = tmm_2v2_rating
            return tmm_2v2_rating
        else:
            return super().__getitem__(key)


class InclusiveRange():
    """
    A simple inclusive range.

    # Examples
    assert 10 in InclusiveRange()
    assert 10 in InclusiveRange(0)
    assert 10 in InclusiveRange(0, 10)
    assert -1 not in InclusiveRange(0, 10)
    assert 11 not in InclusiveRange(0, 10)
    """
    def __init__(self, lo: Optional[float] = None, hi: Optional[float] = None):
        self.lo = lo
        self.hi = hi

    def __contains__(self, rating: float) -> bool:
        if self.lo is not None and rating < self.lo:
            return False
        if self.hi is not None and rating > self.hi:
            return False
        return True

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, type(self))
            and self.lo == other.lo
            and self.hi == other.hi
        )
