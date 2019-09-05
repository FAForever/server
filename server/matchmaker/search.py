import asyncio
import math
import time
from typing import List, Optional, Tuple

from trueskill import Rating, quality

from .. import config
from ..decorators import with_logger
from ..players import Player


@with_logger
class Search:
    """
    Represents the state of a users search for a match.
    """

    def __init__(
        self,
        players: List[Player],
        start_time: Optional[float]=None,
        rating_prop: str='ladder_rating'
    ):
        """
        Default ctor for a search

        :param players: player to use for searching
        :param start_time: optional start time for the search
        :param rating_prop: 'ladder_rating' or 'global_rating'
        :return: the search object
        """
        assert isinstance(players, list)
        for player in players:
            assert getattr(player, rating_prop) is not None

        self.players = players
        self.rating_prop = rating_prop
        self.start_time = start_time or time.time()
        self._match = asyncio.Future()

    @staticmethod
    def adjusted_rating(player: Player):
        """
        Returns an adjusted mean with a simple linear interpolation between current mean and a specified base mean
        """
        mean, dev = player.ladder_rating
        adjusted_mean = ((config.NEWBIE_MIN_GAMES - player.ladder_games) * config.NEWBIE_BASE_MEAN
                         + player.ladder_games * mean) / config.NEWBIE_MIN_GAMES
        return adjusted_mean, dev

    @staticmethod
    def _is_ladder_newbie(player: Player) -> bool:
        return player.ladder_games <= config.NEWBIE_MIN_GAMES

    def is_ladder_search(self) -> bool:
        return self.rating_prop == 'ladder_rating'

    def is_single_party(self) -> bool:
        return len(self.players) == 1

    def is_single_ladder_newbie(self) -> bool:
        return (
            self.is_single_party()
            and self._is_ladder_newbie(self.players[0])
            and self.is_ladder_search()
        )

    def has_no_top_player(self) -> bool:
        max_rating = max(map(lambda rating_tuple: rating_tuple[0], self.ratings))
        return max_rating < config.TOP_PLAYER_MIN_RATING


    @property
    def ratings(self):
        ratings = []
        for player, rating in zip(self.players, self.raw_ratings):
            # New players (less than config.NEWBIE_MIN_GAMES games) match against less skilled opponents
            if self._is_ladder_newbie(player):
                rating = self.adjusted_rating(player)
            ratings.append(rating)
        return ratings

    @property
    def raw_ratings(self):
        return [getattr(player, self.rating_prop) for player in self.players]

    @property
    def boundary_80(self):
        """
        Returns 'boundary' mu values for achieving roughly 80% quality

        These are the mean, rounded to nearest 10, +/- 200, assuming sigma <= 100
        """
        # TODO: Figure out what to do with these boundaries
        mu, _ = self.ratings[0]  # Takes the rating of the first player, only works for 1v1
        rounded_mu = int(math.ceil(mu / 10) * 10)
        return rounded_mu - 200, rounded_mu + 200

    @property
    def boundary_75(self):
        """
        Returns 'boundary' mu values for achieving roughly 75% quality

        These are the mean, rounded to nearest 10, +/- 100, assuming sigma <= 200
        """
        # TODO: Figure out what to do with these boundaries
        mu, _ = self.ratings[0]  # Takes the rating of the first player, only works for 1v1
        rounded_mu = int(math.ceil(mu / 10) * 10)
        return rounded_mu - 100, rounded_mu + 100

    @property
    def search_expansion(self) -> float:
        """
        Defines how much to expand the search range of game quality due to waiting
        time.

        The graph of this function over time looks essentially like this:
                           END (x)-> ___ <- MAX (y)
                                    /
                                ___/ <- START (x)
        The search threshold will not expand until a certain time START has been
        reached. Then it will expand linearly with time until time END, at which
        point it will have reached it's maximum value and will not expand
        further.
        """
        elapsed = time.time() - self.start_time
        MAX = config.LADDER_SEARCH_EXPANSION_MAX
        START = config.LADDER_SEARCH_EXPANSION_START
        END = config.LADDER_SEARCH_EXPANSION_END

        if elapsed < START:
            return 0.0
        if elapsed > END:
            return MAX

        return (MAX / (END - START)) * (elapsed - START)

    @property
    def match_threshold(self) -> float:
        """
        Defines the threshold for game quality
        The base minimum quality is determined as 80% of the quality of a game
        against a copy of yourself.
        This is decreased by self.search_expansion if search is to be expanded.

        :return:
        """

        quality_of_game_against_yourself = self.quality_with(self)
        return max(0.8 * quality_of_game_against_yourself - self.search_expansion, 0)

    def quality_with(self, other: 'Search') -> float:
        assert all(other.raw_ratings)
        assert other.players

        team1 = [Rating(*rating) for rating in self.ratings]
        team2 = [Rating(*rating) for rating in other.ratings]

        return quality([team1, team2])

    @property
    def is_matched(self):
        return self._match.done() and not self._match.cancelled()

    def done(self):
        return self._match.done()

    @property
    def is_cancelled(self):
        return self._match.cancelled()

    def matches_with(self, other: 'Search'):
        """
        Determine if this search is compatible with other given search according to both wishes.
        """
        if not isinstance(other, Search):
            return False
        elif self.quality_with(other) >= self.match_threshold and \
                other.quality_with(self) >= other.match_threshold:
            return True
        return False

    def match(self, other: 'Search'):
        """
        Mark as matched with given opponent
        :param other:
        :return:
        """
        self._logger.info("Matched %s with %s", self.players, other.players)

        for player, raw_rating in zip(self.players, self.raw_ratings):
            if self._is_ladder_newbie(player):
                mean, dev = raw_rating
                adjusted_mean = self.adjusted_rating(player)
                self._logger.info('Adjusted mean rating for {player} with {ladder_games} games from {mean} to {adjusted_mean}'.format(
                    player=player,
                    ladder_games=player.ladder_games,
                    mean=mean,
                    adjusted_mean=adjusted_mean
                ))
        self._match.set_result(other)

    async def await_match(self):
        """
        Wait for this search to complete
        :return:
        """
        await asyncio.wait_for(self._match, None)
        return self._match

    def cancel(self):
        """
        Cancel searching for a match
        :return:
        """
        self._match.cancel()

    def __str__(self):
        return "Search({}, {}, {})".format(self.players, self.match_threshold, self.search_expansion)

Match = Tuple[Search, Search]
