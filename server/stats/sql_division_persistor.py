# coding=utf-8
import asyncio
from server.stats.division_service import *
from server.config import LADDER_SEASON
import server.db as db


class SqlDivisionPersistor(DivisionPersistor):
    """
    SQL implementation of the persistance layer
    """

    def add_player(self, player: 'PlayerDivisionInfo') -> None:
        """
        Add a new player to the division scores
        :param player: new player with zero score and initial league
        """
        async def add_player_async(player: 'PlayerDivisionInfo') -> None:
            async with db.db_pool.get() as conn:
                cursor = await conn.cursor()

                await cursor.execute("INSERT INTO `ladder_division_score` "
                                     "(`season`, `user_id`,`league`, `score`, `games`) VALUES "
                                     "(%s, %s, 1, 0.0, 0)" % (LADDER_SEASON, player.user_id))

        asyncio.ensure_future(add_player_async(player))

    def update_player(self, player: 'PlayerDivisionInfo') -> None:
        """
        Update a player after a game (league, score, games)
        :param player: updated player
        """

        async def update_player_async(self, player: 'PlayerDivisionInfo') -> None:
            async with db.db_pool.get() as conn:
                cursor = await conn.cursor()

                await cursor.execute("UPDATE `ladder_division_score` "
                                     "SET `league` = %s, `score` = %s, `games` = `games` + 1 "
                                     "WHERE user_id = %s AND`season` = %s" %
                                     (player.league, player.score, player.user_id, LADDER_SEASON))

        asyncio.ensure_future(update_player_async(player))