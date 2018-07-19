import asyncio
import time

import math

from server.decorators import with_logger
from trueskill import quality_1vs1, Rating

from server.players import Player


@with_logger
class Search:
    """
    Represents the state of a users search for a match.
    """
    newbie_base_mean = 500 # The base rating for a noob with 0 games
    newbie_game_threshold = 10 # The number of games until rating should be applied fully

    def __init__(self, player, start_time=None, rating_prop='ladder_rating'):
        """
        Default ctor for a search

        :param player: player to use for searching
        :param start_time: optional start time for the search
        :param rating_prop: 'ladder_rating' or 'global_rating'
        :return: the search object
        """
        self.rating_prop = rating_prop
        self.player = player
        assert getattr(self.player, rating_prop) is not None
        self.start_time = start_time or time.time()
        self._match = asyncio.Future()

        # A map from 'deviation above' to 'minimum game quality required'
        # This ensures that new players get matched broadly to
        # give the system a chance at placing them
        self._deviation_quality = {
            450: 0.4,
            350: 0.6,
            300: 0.7,
            250: 0.75,
            0: 0.8
        }

    @property
    def adjusted_rating(self):
        """
        Returns an adjusted mean with a simple linear interpolation between current mean and a specified base mean
        """
        if self.rating_prop=='ladder_rating':
            numgames = self.player.numGames
            if numgames <= self.newbie_game_threshold:
                mean, dev = self.player.ladder_rating
                adjusted_mean = ((self.newbie_game_threshold - numgames) * self.newbie_base_mean + numgames * mean) / self.newbie_game_threshold
                return (adjusted_mean, dev)

    @property
    def rating(self):
        numgames = self.player.numGames
        if numgames <= self.newbie_game_threshold:
            return self.adjusted_rating
        else:
            return getattr(self.player, self.rating_prop)

    @property
    def unadjusted_rating(self):
        return getattr(self.player, self.rating_prop)

    @property
    def boundary_80(self):
        """
        Returns 'boundary' mu values for achieving roughly 80% quality

        These are the mean, rounded to nearest 10, +/- 200, assuming sigma <= 100
        """
        mu, _ = self.rating
        rounded_mu = int(math.ceil(mu/10)*10)
        return rounded_mu - 200, rounded_mu + 200

    @property
    def boundary_75(self):
        """
        Returns 'boundary' mu values for achieving roughly 75% quality

        These are the mean, rounded to nearest 10, +/- 100, assuming sigma <= 200
        """
        mu, _ = self.rating
        rounded_mu = int(math.ceil(mu/10)*10)
        return rounded_mu - 100, rounded_mu + 100

    @property
    def search_expansion(self):
        """
        Defines how much to expand the search range of game quality due to waiting time
        """
        return 0.25 * min(1 / ((time.time() - self.start_time) / 300), 1)

    @property
    def match_threshold(self):
        """
        Defines the threshold for game quality

        :return:
        """
        _, deviation = self.rating

        for d, q in self._deviation_quality.items():
            if deviation >= d:
                return max(q - self.search_expansion, 0)

    def quality_with(self, opponent):
        if not isinstance(opponent, Player):
            raise TypeError("{} is not a valid player to match with".format(opponent))
        if not getattr(opponent, self.rating_prop):
            return 0
        return quality_1vs1(Rating(*self.rating),
                            Rating(*getattr(opponent, self.rating_prop)))

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
        elif self.quality_with(other.player) >= self.match_threshold and \
            other.quality_with(self.player) >= other.match_threshold:
            return True
        return False

    def match(self, other: 'Search'):
        """
        Mark as matched with given opponent
        :param opponent:
        :return:
        """
        self._logger.info("Matched %s with %s", self.player, other.player)
        
        numgames = self.player.numGames
        if numgames <= self.newbie_game_threshold:
            mean, dev = self.unadjusted_rating
            adjusted_mean = self.adjusted_rating
            self._logger.info('Adjusted mean rating for {player} with {numgames} games from {mean} to {adjusted_mean}'.format(
                player=self.player,
                numgames=numgames,
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
        return "Search({}, {}, {})".format(self.player, self.match_threshold, self.search_expansion)
