import asyncio
from collections import OrderedDict
from concurrent.futures import CancelledError
from pybloom import ScalableBloomFilter

from server import PlayerService
from server.decorators import with_logger
from .search import Search


@with_logger
class MatchmakerQueue:
    def __init__(self, queue_name: str, player_service: PlayerService):
        self.player_service = player_service
        self.queue_name = queue_name
        self.rating_prop = 'ladder_rating'
        # A priority queue of currently queuing players
        self.queue = OrderedDict()
        self.filter = ScalableBloomFilter(mode=ScalableBloomFilter.SMALL_SET_GROWTH)
        self._logger.info("MatchmakerQueue initialized for {}, using bloom filter: {}".format(queue_name, self.filter))

    def notify_potential_opponents(self, search: Search):
        """
        Notify opponents who might potentially match the given search object
        :param search:
        :return:
        """
        self._logger.info("Notifying potential opponents")
        for opponent in self.player_service.players:
            if {search.player, opponent} in self.filter:
                opponent.notify_potential_match(search.player)

    def push(self, search: Search):
        """
        Push the given search object onto the queue

        :param search:
        :return:
        """
        self.queue[search.player] = search

    def match(self, s1: Search, s2: Search):
        """
        Mark the given two searches as matched
        :param s1:
        :param s2:
        :return:
        """
        self.filter.add({s1.player, s2.player})
        if (s1.is_matched or s2.is_matched) or (s1.is_cancelled or s2.is_cancelled):
            return
        s1.match(s2)
        s2.match(s1)
        if s1.player in self.queue:
            del self.queue[s1.player]
        if s2.player in self.queue:
            del self.queue[s2.player]

    def __len__(self):
        return self.queue.__len__()

    @asyncio.coroutine
    def search(self, player, start_time=None, search=None):
        """
        Search for a match.

        If a suitable match is found, immediately calls on_matched_with on both players.

        Otherwise, puts a search object into the Queue and awaits completion

        :param player: Player to search for a matchup for
        """
        search = search or Search(player, start_time)
        try:
            self._logger.debug("Searching for matchup for {}".format(player))
            for opponent, opponent_search in self.queue.items():
                if opponent == player:
                    continue
                if {player, opponent} in self.filter\
                        or search.matches_with(opponent_search):
                    self.match(search, opponent_search)
                    return

                quality = search.quality_with(player)
                threshold = search.match_threshold
                self._logger.debug("Game quality between {} and {}: {} (threshold: {})"
                                  .format(player, opponent, quality, threshold))
                if quality >= threshold:
                    self.match(search, opponent_search)
                    return

            self.notify_potential_opponents(search)

            self._logger.debug("Found nobody searching, created new search object in queue: {}".format(search))
            self.queue[player] = search
            yield from search.await_match()
        except CancelledError:
            del self.queue[search.player]
            pass

