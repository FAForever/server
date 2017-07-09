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


class DivisionAccessor(metaclass=ABCMeta):
    """
    Interface for the persistance layer
    """

    @abstractmethod
    async def get_divisions(self) -> List['Division']:
        """
        :return list of divisions
        """
        pass  # pragma: no cover

    @abstractmethod
    async def get_player_infos(self, season: int) -> List['PlayerDivisionInfo']:
        """
        :param season: requested season for all player infos
        :return list of player infos for given season
        """
        pass  # pragma: no cover

    @abstractmethod
    async def add_player(self, season: int, player: 'PlayerDivisionInfo') -> None:
        """
        Add a new player to the persistance layer
        :param player: new player with zero score and initial league
        """
        pass  # pragma: no cover

    @abstractmethod
    async def update_player(self, season: int, player: 'PlayerDivisionInfo') -> None:
        """
        Update a player after a game (league, score, games)
        :param player: updated player
        """
        pass  # pragma: no cover


class DivisionService:
    """
    Division service calculates changes to the ladder leagues & divisions after each game
    """

    def __init__(self, accessor: 'DivisionAccessor', season: int):
        self._divisions = None
        self._players = None
        self.season = season
        self.accessor = accessor

    async def get_divisions(self):
        if self._divisions is None:
            self._divisions = await self.accessor.get_divisions()

        return self._divisions

    async def _ensure_players(self):
        if self._players is None:
            players_infos = await self.accessor.get_player_infos(self.season)
            self._players = dict()

            for info in players_infos:
                self._players[info.user_id] = info

    async def _get_players(self) -> Dict[int, 'PlayerDivisionInfo']:
        await self._ensure_players()

        return self._players

    async def get_player(self, user_id: int):
        return (await self._get_players())[user_id]

    async def add_player(self, player_id: int) -> None:
        await self._ensure_players()

        logger.info("Added new player %s to divisions", player_id)
        self._players[player_id] = PlayerDivisionInfo(player_id, 1, 0.0)
        await self.accessor.add_player(self.season, self._players[player_id])

    async def update_player_stats(self, player: PlayerDivisionInfo, new_score: float) -> None:
        logger.debug("Update score for %s to %s", player)
        player.score = new_score
        await self.accessor.update_player(self.season, player)

    async def promote_player(self, player):
        logger.info("%s got promoted to league %s", player, player.league + 1)
        player.score = 0.0
        player.league += 1
        await self.accessor.update_player(self.season, player)

    async def post_result(self, player_one: int, player_two: int, winning_slot: int) -> None:
        """
        Post a ladder game result to the division system
        :param player_one: FAF User ID of 1st player
        :param player_two: FAF User ID of 2nd player
        :param winning_slot: 0 for draw, 1 for 1st player, 2 for 2nd player
        """
        players = await self._get_players()

        if player_one not in players:
            await self.add_player(self.season, player_one)

        if player_two not in players:
            await self.add_player(self.season, player_two)

        if winning_slot == 0:
            logger.info("Game ended in a draw - no changes in score")
            await self.update_player_stats(self._players[player_one], players[player_one].score)
            await self.update_player_stats(self._players[player_two], players[player_two].score)
            return

        winner = players[player_one] if winning_slot == 1 else players[player_two]
        loser = players[player_two] if winning_slot == 1 else players[player_one]

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

        if winner.score + gain > await self.max_league_threshold(winner.league):
            await self.promote_player(winner)
        else:
            await self.update_player_stats(winner, winner.score + gain)

        await self.update_player_stats(loser, max(0.0, loser.score - loss))

    async def get_player_division(self, user_id: int) -> 'Division':
        player = await self.get_player(user_id)
        return await self.get_division(player.league, player.score)

    async def max_league_threshold(self, league: int) -> float:
        return max([x.threshold for x in await self.get_divisions() if x.league == league])

    async def get_division(self, league: int, score: float) -> Division:
        divisions_of_league = [x for x in await self.get_divisions() if x.league == league]

        for division in sorted(divisions_of_league, key=lambda d: d.threshold):
            if division.threshold > score:
                return division

        logger.error("league %s has no division for score %s", league, score)
        return None
