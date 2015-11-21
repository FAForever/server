import asyncio
from collections import OrderedDict
from concurrent.futures import CancelledError
from pybloom import ScalableBloomFilter

import server
from server.decorators import with_logger
from .search import Search


@with_logger
class MatchmakerQueue:
    def __init__(self, queue_name: str, player_service: "PlayerService", game_service: "GameService"):
        self.player_service = player_service
        self.game_service = game_service
        self.queue_name = queue_name
        self.rating_prop = 'ladder_rating'
        self.queue = OrderedDict()
        self._logger.info("MatchmakerQueue initialized for {}".format(queue_name))

    def notify_potential_opponents(self, search: Search, potential=True):
        """
        Notify opponents who might potentially match the given search object
        :param search: search object to notify for
        :param potential: Whether or not we've started or stopped searching
        :return:
        """
        self._logger.info("Notifying potential opponents")
        for opponent in self.player_service.players.values():
            if opponent == search.player:
                continue
            quality = search.quality_with(opponent)
            if quality >= search.match_threshold:
                opponent.notify_potential_match(search.player, potential)

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
        if (s1.is_matched or s2.is_matched) or (s1.is_cancelled or s2.is_cancelled):
            return
        s1.match(s2)
        s2.match(s1)
        if s1.player in self.queue:
            del self.queue[s1.player]
        if s2.player in self.queue:
            del self.queue[s2.player]
        asyncio.ensure_future(self.game_service.ladder_service.start_game(s1.player, s2.player))

    def __len__(self):
        return self.queue.__len__()

    async def search(self, player, start_time=None, search=None):
        """
        Search for a match.

        If a suitable match is found, immediately calls on_matched_with on both players.

        Otherwise, puts a search object into the Queue and awaits completion

        :param player: Player to search for a matchup for
        """
        search = search or Search(player, start_time)
        with server.stats.timer('matchmaker.search'):
            try:
                self._logger.debug("Searching for matchup for {}".format(player))
                for opponent, opponent_search in self.queue.items():
                    if opponent == player:
                        continue

                    quality = search.quality_with(player)
                    threshold = search.match_threshold
                    self._logger.debug("Game quality between {} and {}: {} (threshold: {})"
                                        .format(player, opponent, quality, threshold))
                    if quality >= threshold:
                        self.match(search, opponent_search)
                        return

                self.notify_potential_opponents(search, True)

                self._logger.debug("Found nobody searching, pushing to queue: {}".format(search))
                self.queue[player] = search
                await search.await_match()
                self._logger.debug("Search complete".format(search))
                self.notify_potential_opponents(search, False)
                del self.queue[search.player]
            except CancelledError:
                pass

