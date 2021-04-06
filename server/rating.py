"""
Type definitions for player ratings
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, TypeVar, Union

import trueskill

from server.config import config
from server.weakattr import WeakAttribute

Rating = Tuple[float, float]
V = TypeVar("V")


@dataclass(init=False)
class Leaderboard():
    id: int
    technical_name: str
    # Need the type annotation here so that the dataclass decorator sees it as
    # a field and includes it in generated methods (such as __eq__)
    initializer: WeakAttribute["Leaderboard"] = WeakAttribute["Leaderboard"]()

    def __init__(
        self,
        id: int,
        technical_name: str,
        initializer: Optional["Leaderboard"] = None
    ):
        self.id = id
        self.technical_name = technical_name
        if initializer:
            self.initializer = initializer

    def __repr__(self) -> str:
        initializer = self.initializer
        initializer_name = "None"
        if initializer:
            initializer_name = initializer.technical_name
        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, technical_name={self.technical_name}, "
            f"initializer={initializer_name})"
        )


# Some places have references to these ratings hardcoded.
class RatingType():
    GLOBAL = "global"
    LADDER_1V1 = "ladder_1v1"


class PlayerRatings(Dict[str, Rating]):
    def __init__(self, leaderboards: Dict[str, Leaderboard]):
        self.leaderboards = leaderboards

    def __setitem__(
        self,
        rating_type: str,
        value: Union[Rating, trueskill.Rating]
    ) -> None:
        if isinstance(value, trueskill.Rating):
            val = (value.mu, value.sigma)
        else:
            val = value
        super().__setitem__(rating_type, val)

    def __getitem__(self, rating_type: str) -> Rating:
        if rating_type not in self:
            rating = self._get_initial_rating(rating_type)

            self[rating_type] = rating
            return rating

        return super().__getitem__(rating_type)

    def _get_initial_rating(self, rating_type: str) -> Rating:
        """Create an initial rating when no rating exists yet."""
        leaderboard = self.leaderboards.get(rating_type)
        if leaderboard is None or leaderboard.initializer is None:
            return default_rating()

        rating = self.get(leaderboard.initializer.technical_name)
        if rating is None:
            return default_rating()

        mean, dev = rating
        if dev > 250:
            return (mean, dev)

        return (mean, min(dev + 150, 250))


def default_rating() -> Rating:
    return (config.START_RATING_MEAN, config.START_RATING_DEV)


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
