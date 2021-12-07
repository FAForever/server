"""
Type definitions for player ratings
"""

from dataclasses import dataclass
from typing import NamedTuple, Optional, Union

import trueskill

from server.config import config
from server.weakattr import WeakAttribute

AnyRating = Union["Rating", trueskill.Rating, tuple[float, float]]


class Rating(NamedTuple):
    """
    A container for holding a mean, deviation pair and computing the displayed
    rating.

    Uses mean, dev to differentiate from the trueskill.Rating type which uses
    mu, sigma.
    """
    mean: float
    dev: float

    def of(value: AnyRating) -> "Rating":
        if isinstance(value, trueskill.Rating):
            return Rating(value.mu, value.sigma)
        elif isinstance(value, Rating):
            return value

        return Rating(*value)

    def displayed(self) -> float:
        return self.mean - 3 * self.dev


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


class PlayerRatings(dict[str, Rating]):
    def __init__(self, leaderboards: dict[str, Leaderboard], init: bool = True):
        self.leaderboards = leaderboards
        # Rating types which are present but should be recomputed.
        self.transient: set[str] = set()
        # Rating types which have been computed since the last rating update
        self.clean: set[str] = set()

        # DEPRECATED: Initialize known rating types so the client can display them
        if init:
            _ = self[RatingType.GLOBAL]
            _ = self[RatingType.LADDER_1V1]

    def __setitem__(self, rating_type: str, value: AnyRating) -> None:
        self.transient.discard(rating_type)
        # This could be optimized further by walking backwards along the
        # initialization chain and only unmarking the ratings we come accross,
        # but this adds complexity so we won't bother unless it really becomes
        # a performance bottleneck, which is unlikely.
        self.clean.clear()
        super().__setitem__(rating_type, Rating.of(value))

    def __getitem__(
        self,
        rating_type: str,
        history: Optional[set[str]] = None,
    ) -> Rating:
        history = history or set()
        entry = self.get(rating_type)

        if (
            entry is None or
            (rating_type not in self.clean and rating_type in self.transient)
        ):
            # Check for cycles
            if rating_type in history:
                return default_rating()

            rating = self._get_initial_rating(rating_type, history=history)

            self.transient.add(rating_type)
            self.clean.add(rating_type)
            super().__setitem__(rating_type, rating)
            return rating

        return super().__getitem__(rating_type)

    def _get_initial_rating(
        self,
        rating_type: str,
        history: set[str],
    ) -> Rating:
        """Create an initial rating when no rating exists yet."""
        leaderboard = self.leaderboards.get(rating_type)
        if leaderboard is None or leaderboard.initializer is None:
            return default_rating()

        history.add(rating_type)
        init_rating_type = leaderboard.initializer.technical_name
        rating = self.__getitem__(init_rating_type, history=history)

        if rating.dev > 250 or init_rating_type in self.transient:
            return rating

        return Rating(rating.mean, min(rating.dev + 150, 250))

    def update(self, other: dict[str, Rating]):
        self.transient -= set(other)
        self.clean.clear()
        if isinstance(other, PlayerRatings):
            self.transient |= other.transient
        else:
            other = {key: Rating.of(value) for key, value in other.items()}
        super().update(other)


def default_rating() -> Rating:
    return Rating(config.START_RATING_MEAN, config.START_RATING_DEV)


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
