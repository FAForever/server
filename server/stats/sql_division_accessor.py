# coding=utf-8
from server.stats.division_service import *
import server.db as db


class SqlDivisionAccessor(DivisionAccessor):
    """
    SQL implementation of the persistance layer
    """

    async def get_divisions(self) -> List['Division']:
        """
        :return list of divisions in the database
        """
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            division_rows = await cursor.execute("SELECT `id`, `name`, `league`, `threshold` FROM `ladder_division` ")
            divisions = []
            for id, name, league, threshold in division_rows:
                divisions.append(Division(id, name, league, threshold))

            return divisions

    async def get_player_infos(self, season: int) -> List['PlayerDivisionInfo']:
        """
        :param season: requested season for all player infos
        :return list of player infos for given season
        """
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            player_rows = await cursor.execute("SELECT `user_id`, `league`, `score` FROM `ladder_division_score` "
                                               "WHERE `season` = %s" % season)
            player_infos = []
            for user_id, league, score in player_rows:
                player_infos.append(PlayerDivisionInfo(user_id, league, score))

            return player_infos

    async def add_player(self, season: int, player: 'PlayerDivisionInfo') -> None:
        """
        Add a new player to the division scores
        :param player: new player with zero score and initial league
        """
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            await cursor.execute("INSERT INTO `ladder_division_score` "
                                 "(`season`, `user_id`,`league`, `score`, `games`) VALUES "
                                 "(%s, %s, 1, 0.0, 0)" % (season, player.user_id))

    async def update_player(self, season: int, player: 'PlayerDivisionInfo') -> None:
        """
        Update a player after a game (league, score, games)
        :param player: updated player
        """
        async with db.db_pool.get() as conn:
            cursor = await conn.cursor()

            await cursor.execute("UPDATE `ladder_division_score` "
                                 "SET `league` = %s, `score` = %s, `games` = `games` + 1 "
                                 "WHERE user_id = %s AND`season` = %s" %
                                 (player.league, player.score, player.user_id, season))
