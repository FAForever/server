import logging
import asyncio

import server.db as db
from server.abc.base_game import InitMode
from server.players import PlayerState, Player

logger = logging.getLogger(__name__)

from .game import Game, ValidityState

from PySide.QtSql import QSqlQuery
import operator
import config


class LadderGame(Game):
    """Class for 1v1 ladder game"""
    init_mode = InitMode.AUTO_LOBBY
    
    def __init__(self, id, *args, **kwargs):
        super(self.__class__, self).__init__(id, *args, **kwargs)

        self.max_players = 2
        self.leagues = {}

    def setLeaguePlayer(self, player):
        self.leagues[player.login] = player.league

    def rate_game(self):
        if self.validity == ValidityState.VALID:
            new_ratings = self.compute_rating()
            self.persist_rating_change_stats(new_ratings, rating='ladder1v1')

    def is_winner(self, player: Player):
        return self.get_army_result(self.get_player_option(player.id, 'Army')) > 0

    def on_game_end(self):
        super().on_game_end()
        if self.validity != ValidityState.VALID:
            return
        asyncio.async(self._on_game_end())

    @asyncio.coroutine
    def _on_game_end(self):
        if self.is_draw:
            with (yield from db.db_pool) as conn:
                with (yield from conn.cursor()) as cursor:
                    yield from cursor.execute("UPDATE table_map_features SET num_draws = (num_draws +1) "
                                              "WHERE map_id = %s", (self.map_id, ))
            return

        evenLeague = True
        maxleague = max(iter(self.leagues.items()), key=operator.itemgetter(1))[1]
        if len(set(self.leagues.values())) != 1:
            evenLeague = False

        with (yield from db.db_pool) as conn:
            with (yield from conn.cursor()) as cursor:
                for player in self.players:
                    if self.is_winner(player):
                        # if not even league:
                        scoreToAdd = 1
                        if not evenLeague:
                            if self.leagues[player] == maxleague:
                                scoreToAdd = 0.5
                            else:
                                scoreToAdd = 1.5

                        yield from cursor.execute("UPDATE {} "
                                                  "SET score = (score + %s) "
                                                  "WHERE idUser = %s".format(config.LADDER_SEASON),
                                                  (scoreToAdd, player.id))
                    else:
                        # if not even league:
                        scoreToRemove = 0.5
                        if not evenLeague:
                            if self.leagues[player] == maxleague:
                                scoreToRemove = 1
                            else:
                                scoreToRemove = 0

                        yield from cursor.execute("UPDATE {} "
                                                  "SET score = GREATEST(0, (score - %s))"
                                                  "WHERE idUser = %s".format(config.LADDER_SEASON),
                                                  (scoreToRemove, player.id))

                    yield from cursor.execute("SELECT league, score FROM {}"
                                              "WHERE `idUser` = %s".format(config.LADDER_SEASON),
                                              (player.id, ))
                    if cursor.rowcount == 0:
                        pleague, pscore = yield from cursor.fetchone()
                        # Minimum scores, by league, to move to next league
                        league_incr_min = {1: 50, 2: 75, 3: 100, 4: 150}
                        if pleague in league_incr_min and pscore > league_incr_min[pleague]:
                            yield from cursor.execute("UPDATE {} SET league = league+1, score = 0"
                                                      "WHERE `idUser` = %s".format(config.LADDER_SEASON),
                                                      (player.id, ))

                        for p in self.players:
                            yield from cursor.execute("SELECT score, league "
                                                      "FROM {} "
                                                      "WHERE idUser = %s".format(config.LADDER_SEASON),
                                                      (player.id, ))
                            if cursor.rowcount > 0:
                                score, p.league = yield from cursor.fetchone()

                                yield from cursor.execute("SELECT name, `limit` "
                                                          "FROM `ladder_division` "
                                                          "WHERE `league` = ? AND `limit` >= ?"
                                                          "ORDER BY `limit` ASC LIMIT 1",
                                                          (p.league, score))
                                if cursor.rowcount > 0:
                                    p.division, _ = yield from cursor.fetchone()

    @property
    def is_draw(self):
        for army in self.armies:
            for result in self._results[army]:
                if result[1] == 'draw':
                    return True
        return False

    def get_army_result(self, army):
        """
        The head-to-head matchup ranking uses only win/loss as a factor
        :param army:
        :return:
        """
        for result in self._results[army]:
            if result[1] == 'victory':
                return 1
        return 0


