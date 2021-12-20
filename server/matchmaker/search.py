import asyncio
import itertools
import math
import statistics
import time
from typing import Any, Callable, Optional

import trueskill

from server.rating import Rating, RatingType

from ..config import config
from ..decorators import with_logger
from ..players import Player

Match = tuple["Search", "Search"]
OnMatchedCallback = Callable[["Search", "Search"], Any]


def get_average_rating(searches):
    return statistics.mean(itertools.chain(*[s.displayed_ratings for s in searches]))


@with_logger
class Search:
    """
    Represents the state of a users search for a match.
    """

    def __init__(
        self,
        players: list[Player],
        start_time: Optional[float] = None,
        rating_type: str = RatingType.LADDER_1V1,
        on_matched: OnMatchedCallback = lambda _1, _2: None
    ):
        assert isinstance(players, list)
        for player in players:
            assert player.ratings[rating_type] is not None

        self.players = players
        self.rating_type = rating_type
        self.start_time = start_time or time.time()
        self._match = asyncio.get_event_loop().create_future()
        self._failed_matching_attempts = 0
        self.on_matched = on_matched

        # Precompute this
        self.quality_against_self = self.quality_with(self)

    def adjusted_rating(self, player: Player) -> Rating:
        """
        Returns an adjusted mean with a simple linear interpolation between current mean and a specified base mean
        """
        mean, dev = player.ratings[self.rating_type]
        game_count = player.game_count[self.rating_type]
        adjusted_mean = ((config.NEWBIE_MIN_GAMES - game_count) * config.NEWBIE_BASE_MEAN
                         + game_count * mean) / config.NEWBIE_MIN_GAMES
        return Rating(adjusted_mean, dev)

    def is_newbie(self, player: Player) -> bool:
        return player.game_count[self.rating_type] <= config.NEWBIE_MIN_GAMES

    def is_single_party(self) -> bool:
        return len(self.players) == 1

    def has_newbie(self) -> bool:
        for player in self.players:
            if self.is_newbie(player):
                return True

        return False

    def num_newbies(self) -> int:
        return sum(self.is_newbie(player) for player in self.players)

    def has_high_rated_player(self) -> bool:
        max_rating = max(self.displayed_ratings)
        return max_rating >= config.HIGH_RATED_PLAYER_MIN_RATING

    def has_top_player(self) -> bool:
        max_rating = max(self.displayed_ratings)
        return max_rating >= config.TOP_PLAYER_MIN_RATING

    @property
    def ratings(self) -> list[Rating]:
        ratings = []
        for player, rating in zip(self.players, self.raw_ratings):
            # New players (less than config.NEWBIE_MIN_GAMES games) match against less skilled opponents
            if self.is_newbie(player):
                rating = self.adjusted_rating(player)
            ratings.append(rating)
        return ratings

    @property
    def cumulative_rating(self) -> float:
        return sum(self.displayed_ratings)

    @property
    def average_rating(self) -> float:
        return statistics.mean(self.displayed_ratings)

    @property
    def raw_ratings(self) -> list[Rating]:
        return [player.ratings[self.rating_type] for player in self.players]

    @property
    def displayed_ratings(self) -> list[float]:
        """
        The client always displays mean - 3 * dev as a player's rating.
        So generally this is perceived as a player's true rating.
        """
        return [rating.displayed() for rating in self.raw_ratings]

    @property
    def failed_matching_attempts(self) -> int:
        return self._failed_matching_attempts

    @property
    def search_expansion(self) -> float:
        """
        Defines how much to expand the search range of game quality due to waiting
        time.

        The threshold will expand linearly with every failed matching attempt
        until it reaches the specified MAX.

        Top players use bigger values to make matching easier.
        """
        if self.has_top_player():
            return min(
                self._failed_matching_attempts * config.LADDER_TOP_PLAYER_SEARCH_EXPANSION_STEP,
                config.LADDER_TOP_PLAYER_SEARCH_EXPANSION_MAX
            )
        else:
            return min(
                self._failed_matching_attempts * config.LADDER_SEARCH_EXPANSION_STEP,
                config.LADDER_SEARCH_EXPANSION_MAX
            )

    def register_failed_matching_attempt(self):
        """
        Signal that matchmaker tried to match this search but was unsuccessful
        and increase internal counter by one.
        """

        self._failed_matching_attempts += 1

    @property
    def match_threshold(self) -> float:
        """
        Defines the threshold for game quality

        The base minimum quality is determined as 80% of the quality of a game
        against a copy of yourself. This is decreased by `self.search_expansion`
        if search is to be expanded.
        """

        return max(0.8 * self.quality_against_self - self.search_expansion, 0)

    def quality_with(self, other: "Search") -> float:
        assert all(other.raw_ratings)
        assert other.players

        team1 = [trueskill.Rating(*rating) for rating in self.ratings]
        team2 = [trueskill.Rating(*rating) for rating in other.ratings]

        return trueskill.quality([team1, team2])

    @property
    def is_matched(self) -> bool:
        return self._match.done() and not self._match.cancelled()

    def done(self) -> bool:
        return self._match.done()

    @property
    def is_cancelled(self) -> bool:
        return self._match.cancelled()

    def matches_with(self, other: "Search") -> bool:
        """
        Determine if this search is compatible with other given search according
        to both wishes.
        """
        if not isinstance(other, Search):
            return False

        quality = self.quality_with(other)
        return self._match_quality_acceptable(other, quality)

    def _match_quality_acceptable(self, other: "Search", quality: float) -> bool:
        """
        Determine if the given match quality is acceptable.

        This gets it's own function so we can call it from the Matchmaker using
        a cached `quality` value.
        """
        # NOTE: We are assuming for optimization purposes that quality is
        # symmetric. If this ever changes, update here
        return (quality >= self.match_threshold and
                quality >= other.match_threshold)

    def match(self, other: "Search"):
        """
        Mark as matched with given opponent
        """
        self._logger.info("Matched %s with %s", self, other)

        self.on_matched(self, other)

        for player, raw_rating in zip(self.players, self.raw_ratings):
            if self.is_newbie(player):
                mean, dev = raw_rating
                adjusted_mean, adjusted_dev = self.adjusted_rating(player)
                self._logger.info(
                    "Adjusted mean rating for %s with %d games from %.1f to %.1f",
                    player.login,
                    player.game_count[self.rating_type],
                    mean,
                    adjusted_mean
                )
        self._match.set_result(other)

    async def await_match(self):
        """
        Wait for this search to complete
        """
        await asyncio.wait_for(self._match, None)
        return self._match

    def cancel(self):
        """
        Cancel searching for a match
        """
        self._match.cancel()

    def __str__(self) -> str:
        return (
            f"Search({self.rating_type}, {self._players_repr()}, threshold="
            f"{self.match_threshold:.2}, expansion={self.search_expansion:.2})"
        )

    def _players_repr(self) -> str:
        contents = ', '.join(
            f"Player({p.login}, {p.id}, {p.ratings[self.rating_type]})"
            for p in self.players
        )
        return f"[{contents}]"

    def __repr__(self) -> str:
        """For debugging"""
        return (
            f"Search({[p.login for p in self.players]}, {self.average_rating}"
            f"{f', FMA: {self.failed_matching_attempts}' if self.failed_matching_attempts else ''}"
            f"{', has_newbie)' if self.has_newbie() else ')'}"
        )

    def get_original_searches(self) -> list["Search"]:
        """
        Returns the searches of which this Search is comprised,
        as if it were a CombinedSearch of one
        """
        return [self]


class CombinedSearch(Search):
    def __init__(self, *searches: Search):
        assert searches
        rating_type = searches[0].rating_type
        assert all(map(lambda s: s.rating_type == rating_type, searches))

        self.rating_type = rating_type
        self.searches = searches

    @property
    def players(self) -> list[Player]:
        return list(itertools.chain(*[s.players for s in self.searches]))

    @property
    def ratings(self) -> list[Rating]:
        return list(itertools.chain(*[s.ratings for s in self.searches]))

    @property
    def cumulative_rating(self) -> float:
        return sum(s.cumulative_rating for s in self.searches)

    @property
    def average_rating(self) -> float:
        return get_average_rating(self.searches)

    @property
    def raw_ratings(self) -> list[Rating]:
        return list(itertools.chain(*[s.raw_ratings for s in self.searches]))

    @property
    def displayed_ratings(self) -> list[float]:
        return list(itertools.chain(*[s.displayed_ratings for s in self.searches]))

    @property
    def failed_matching_attempts(self) -> int:
        return max(search.failed_matching_attempts for search in self.searches)

    def register_failed_matching_attempt(self):
        for search in self.searches:
            search.register_failed_matching_attempt()

    @property
    def match_threshold(self) -> float:
        """
        Defines the threshold for game quality
        """
        return min(s.match_threshold for s in self.searches)

    @property
    def is_matched(self) -> bool:
        return all(s.is_matched for s in self.searches)

    def done(self) -> bool:
        return all(s.done() for s in self.searches)

    @property
    def is_cancelled(self) -> bool:
        return any(s.is_cancelled for s in self.searches)

    def match(self, other: "Search"):
        """
        Mark as matched with given opponent
        """
        self._logger.info("Combined search matched %s with %s", self.players, other.players)

        for s in self.searches:
            s.match(other)

    async def await_match(self):
        """
        Wait for this search to complete
        """
        await asyncio.wait({s.await_match() for s in self.searches})

    def cancel(self):
        """
        Cancel searching for a match
        """
        for s in self.searches:
            s.cancel()

    def __str__(self):
        return f"CombinedSearch({','.join(str(s) for s in self.searches)})"

    def get_original_searches(self) -> list[Search]:
        """
        Returns the searches of which this CombinedSearch is comprised
        """
        return list(self.searches)
