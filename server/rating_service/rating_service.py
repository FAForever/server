from typing import Dict
from server.db import FAFDatabase
from server.decorators import with_logger

from server.players import Player, PlayerState
from server.games.game import GameState, GameError
from server.games.game_results import GameOutcome

from server.rating import RatingType
from trueskill import Rating
from .game_rater import GameRater

@with_logger
class RatingService:
    """
    Service responsible for calculating and saving trueskill rating updates.
    To avoid race conditions, rating updates from a single game ought to be
    atomic.
    """
    def __init__(self, database: FAFDatabase):
        self._db = database

    def _compute_rating(self, game, rating=RatingType.GLOBAL) -> Dict[Player, Rating]:
        """
        Compute new ratings
        :param rating: Rating type
        :return: rating groups of the form:
        >>> p1,p2,p3,p4 = Player()
        >>> [{p1: p1.rating, p2: p2.rating}, {p3: p3.rating, p4: p4.rating}]
        """
        assert game.state is GameState.LIVE or game.state is GameState.ENDED

        if None in game.teams:
            raise GameError(
                "Missing team for at least one player. (player, team): {}"
                .format([(player, game.get_player_option(player.id, 'Team'))
                        for player in game.players])
            )

        outcome_by_player = {
            player: game.get_player_outcome(player)
            for player in game.players
        }

        rater = GameRater(game.players_by_team, outcome_by_player, rating)
        return rater.compute_rating()

    async def _persist_rating_change_stats(
        self, game, rating_groups, rating=RatingType.GLOBAL
    ):
        """
        Persist computed ratings to the respective players' selected rating
        :param rating_groups: of the form returned by Game.compute_rating
        :return: None
        """
        self._logger.info("Saving rating change stats")
        new_ratings = {
            player: new_rating
            for team in rating_groups for player, new_rating in team.items()
        }

        async with self._db.acquire() as conn:
            for player, new_rating in new_ratings.items():
                self._logger.debug(
                    "New %s rating for %s: %s", rating.value, player,
                    new_rating
                )
                player.ratings[rating] = new_rating
                await conn.execute(
                    "UPDATE game_player_stats "
                    "SET after_mean = %s, after_deviation = %s, scoreTime = NOW() "
                    "WHERE gameId = %s AND playerId = %s",
                    (new_rating.mu, new_rating.sigma, game.id, player.id)
                )
                player.game_count[rating] += 1

                await self._update_rating_table(
                    game, conn, rating, player, new_rating
                )

                game.game_service.player_service.mark_dirty(player)

    async def _update_rating_table(
        self, game, conn, rating: RatingType, player: Player, new_rating
    ):
        # If we are updating the ladder1v1_rating table then we also need to update
        # the `winGames` column which doesn't exist on the global_rating table
        table = f'{rating.value}_rating'

        if rating is RatingType.LADDER_1V1:
            is_victory = game.get_player_outcome(player) is GameOutcome.VICTORY
            await conn.execute(
                "UPDATE ladder1v1_rating "
                "SET mean = %s, is_active=1, deviation = %s, numGames = numGames + 1, winGames = winGames + %s "
                "WHERE id = %s", (
                    new_rating.mu, new_rating.sigma, 1 if is_victory else 0,
                    player.id
                )
            )
        else:
            await conn.execute(
                "UPDATE " + table + " "
                "SET mean = %s, is_active=1, deviation = %s, numGames = numGames + 1 "
                "WHERE id = %s", (new_rating.mu, new_rating.sigma, player.id)
            )


    def shutdown(self):
        """
        Finish rating all remaining games, then exit.
        """
        pass
