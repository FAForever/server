# coding=utf-8
import logging
from abc import ABCMeta, abstractmethod
from typing import List, Dict

logger = logging.getLogger(__name__)


class Division:
    def __init__(self, id: int, name: str, league: int, threshold: float):
        self.id = id
        self.name = name
        self.league = league
        self.threshold = threshold


class PlayerDivisionInfo:
    def __init__(self, user_id: int, current_league: int, current_score: float):
        self.user_id = user_id
        self.league = current_league
        self.score = current_score

    def is_in_inferior_league(self, compared_to: 'PlayerDivisionInfo') -> bool:
        return self.league < compared_to.league

    def is_in_superior_league(self, compared_to: 'PlayerDivisionInfo') -> bool:
        return self.league > compared_to.league

    def __str__(self):
        return "PlayerDivisionInfo(user_id=%s, league=%s, score=%s)" % (self.user_id, self.league, self.score)


class DivisionPersistor(ABCMeta):
    """
    Interface for the persistance layer
    """

    @abstractmethod
    def add_player(self, player: 'PlayerDivisionInfo') -> None:
        """
        Add a new player to the persistance layer
        :param player: new player with zero score and initial league
        """
        pass

    @abstractmethod
    def update_player(self, player: 'PlayerDivisionInfo') -> None:
        """
        Update a player after a game (league, score, games)
        :param player: updated player
        """
        pass


class DivisionService:
    """
    Division service calculates changes to the ladder leagues & divisions after each game
    """

    def __init__(self, divisions: List['Division'], player_division_infos: List['PlayerDivisionInfo'],
                 persistor: 'DivisionPersistor'):
        self.divisions = divisions
        self.players = dict()  # type: Dict[int, 'PlayerDivisionInfo']
        self.persistor = persistor

        for info in player_division_infos:
            self.players[info.user_id] = info

    def add_player(self, player_id: int) -> None:
        logger.info("Added new player %s to divisions", player_id)
        self.players[player_id] = PlayerDivisionInfo(player_id, 1, 0.0)
        self.persistor.add_player(self.players[player_id])

    def update_player_stats(self, player: PlayerDivisionInfo, new_score: float) -> None:
        logger.debug("Update score for %s to %s", player)
        player.score = new_score
        self.persistor.update_player(player)

    def promote_player(self, player):
        logger.info("%s got promoted to league %s", player, player.league + 1)
        player.score = 0.0
        player.league += 1
        self.persistor.update_player(player)

    def post_result(self, player_one: int, player_two: int, winning_slot: int) -> None:
        """
        Post a ladder game result to the division system
        :param player_one: FAF User ID of 1st player
        :param player_two: FAF User ID of 2nd player
        :param winning_slot: 0 for draw, 1 for 1st player, 2 for 2nd player
        """
        if player_one not in self.players:
            self.add_player(player_one)

        if player_two not in self.players:
            self.add_player(player_two)

        if winning_slot == 0:
            logger.info("Game ended in a draw - no changes in score")
            self.update_player_stats(self.players[player_one], self.players[player_one].score)
            self.update_player_stats(self.players[player_two], self.players[player_two].score)
            return

        winner = self.players[player_one] if winning_slot == 1 else self.players[player_two]
        loser = self.players[player_two] if winning_slot == 1 else self.players[player_one]

        if winner.is_in_inferior_league(loser):
            gain = 1.5
            loss = 1.0
        elif winner.is_in_superior_league(loser):
            gain = 0.5
            loss = 0.5
        else:
            gain = 1.0
            loss = 0.5

        logger.info("%s won against %s - gain: %s - loss: %s", winner, loser, gain, loss)

        if winner.score + gain > self.max_league_threshold(winner.league):
            self.promote_player(winner)
        else:
            self.update_player_stats(winner, winner.score + gain)

        self.update_player_stats(loser, max(0.0, loser.score - loss))

    def get_player_division(self, player_id: int) -> 'Division':
        player = self.players[player_id]
        return self.get_division(player.league, player.score)

    def max_league_threshold(self, league: int) -> float:
        return max([x.threshold for x in self.divisions if x.league == league])

    def get_division(self, league: int, score: float) -> Division:
        divisions_of_league = [x for x in self.divisions if x.league == league]

        for division in sorted(divisions_of_league, key=lambda d: d.threshold):
            if division.threshold > score:
                return division

        logger.error("league %s has no division for score %s", league, score)
        return None
