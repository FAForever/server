"""
Type definitions for player ratings
"""

from dataclasses import dataclass
from typing import Dict, Optional, Set, Tuple, TypeVar, Union

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
    def __init__(self, leaderboards: Dict[str, Leaderboard], init: bool = True):
        self.leaderboards = leaderboards
        # Rating types which are present but should be recomputed.
        self.transient: Set[str] = set()

        # DEPRECATED: Initialize known rating types so the client can display them
        if init:
            _ = self[RatingType.GLOBAL]
            _ = self[RatingType.LADDER_1V1]

    def __setitem__(
        self,
        rating_type: str,
        value: Union[Rating, trueskill.Rating],
    ) -> None:
        if isinstance(value, trueskill.Rating):
            rating = (value.mu, value.sigma)
        else:
            rating = value

        self.transient.discard(rating_type)
        super().__setitem__(rating_type, rating)

    def __getitem__(
        self,
        rating_type: str,
        history: Optional[Set[str]] = None,
    ) -> Rating:
        history = history or set()
        entry = self.get(rating_type)

        if entry is None or rating_type in self.transient:
            # Check for cycles
            if rating_type in history:
                return default_rating()

            rating = self._get_initial_rating(rating_type, history=history)

            self.transient.add(rating_type)
            super().__setitem__(rating_type, rating)
            return rating

        return super().__getitem__(rating_type)

    def _get_initial_rating(
        self,
        rating_type: str,
        history: Set[str],
    ) -> Rating:
        """Create an initial rating when no rating exists yet."""
        leaderboard = self.leaderboards.get(rating_type)
        if leaderboard is None or leaderboard.initializer is None:
            return default_rating()

        history.add(rating_type)
        init_rating_type = leaderboard.initializer.technical_name
        mean, dev = self.__getitem__(init_rating_type, history=history)

        if dev > 250 or init_rating_type in self.transient:
            return (mean, dev)

        return (mean, min(dev + 150, 250))

    def update(self, other: Dict[str, Rating]):
        self.transient -= set(other)
        if isinstance(other, PlayerRatings):
            self.transient |= other.transient
        super().update(other)


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
