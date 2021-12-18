"""
Manages connected and authenticated players
"""

import contextlib
from typing import Optional, ValuesView

import aiocron
from sqlalchemy import and_, select
from trueskill import Rating

import server.metrics as metrics
from server.db import FAFDatabase
from server.decorators import with_logger
from server.players import Player
from server.rating import RatingType

from .core import Service
from .db.models import (
    avatars,
    avatars_list,
    clan,
    clan_membership,
    global_rating,
    group_permission,
    group_permission_assignment,
    ladder1v1_rating,
    leaderboard,
    leaderboard_rating,
    login,
    user_group,
    user_group_assignment
)


@with_logger
class PlayerService(Service):
    def __init__(self, database: FAFDatabase):
        self._db = database
        self._players = dict()

        # Static-ish data fields.
        self.uniqueid_exempt = {}
        self._dirty_players = set()

    async def initialize(self) -> None:
        await self.update_data()
        self._update_cron = aiocron.crontab(
            "*/10 * * * *", func=self.update_data
        )

    def __len__(self):
        return len(self._players)

    def __iter__(self):
        return self._players.values().__iter__()

    def __getitem__(self, player_id: int) -> Optional[Player]:
        return self._players.get(player_id)

    def __setitem__(self, player_id: int, player: Player):
        self._players[player_id] = player
        metrics.players_online.set(len(self._players))

    @property
    def all_players(self) -> ValuesView[Player]:
        return self._players.values()

    def mark_dirty(self, player: Player):
        self._dirty_players.add(player)

    def pop_dirty_players(self) -> set[Player]:
        dirty_players = self._dirty_players
        self._dirty_players = set()

        return dirty_players

    async def fetch_player_data(self, player):
        async with self._db.acquire() as conn:
            result = await conn.execute(
                select([user_group.c.technical_name])
                .select_from(user_group_assignment.join(user_group))
                .where(user_group_assignment.c.user_id == player.id)
            )
            player.user_groups = {row.technical_name for row in result}

            sql = select([
                avatars_list.c.url,
                avatars_list.c.tooltip,
                clan.c.tag
            ], use_labels=True).select_from(
                login
                .outerjoin(clan_membership)
                .outerjoin(clan)
                .outerjoin(
                    avatars,
                    onclause=and_(
                        avatars.c.idUser == login.c.id,
                        avatars.c.selected == 1
                    )
                )
                .outerjoin(avatars_list)
            ).where(login.c.id == player.id)  # yapf: disable

            result = await conn.execute(sql)
            row = result.fetchone()
            if not row:
                self._logger.warning(
                    "Did not find data for player with id %i",
                    player.id
                )
                return

            row = row._mapping
            player.clan = row.get(clan.c.tag)

            url, tooltip = (
                row.get(avatars_list.c.url),
                row.get(avatars_list.c.tooltip)
            )
            if url and tooltip:
                player.avatar = {"url": url, "tooltip": tooltip}

            await self._fetch_player_ratings(player, conn)

    async def _fetch_player_ratings(self, player, conn):
        sql = select([
            leaderboard_rating.c.mean,
            leaderboard_rating.c.deviation,
            leaderboard_rating.c.total_games,
            leaderboard.c.technical_name,
        ]).select_from(
            leaderboard.join(leaderboard_rating)
        ).where(
            leaderboard_rating.c.login_id == player.id
        )
        result = await conn.execute(sql)

        retrieved_ratings = {
            row.technical_name: (
                (row.mean, row.deviation),
                row.total_games
            )
            for row in result
        }
        for rating_type, (rating, total_games) in retrieved_ratings.items():
            player.ratings[rating_type] = rating
            player.game_count[rating_type] = total_games

        types_not_found = [
            rating_type for rating_type in (
                RatingType.GLOBAL, RatingType.LADDER_1V1
            )
            if rating_type not in retrieved_ratings
        ]
        await self._fetch_player_legacy_rating(player, types_not_found, conn)

    async def _fetch_player_legacy_rating(self, player, rating_types, conn):
        if not rating_types:
            return

        sql = select(
            [
                global_rating.c.mean, global_rating.c.deviation,
                global_rating.c.numGames,
                ladder1v1_rating.c.mean, ladder1v1_rating.c.deviation,
                ladder1v1_rating.c.numGames,
            ], use_labels=True
        ).select_from(
            login.outerjoin(ladder1v1_rating).outerjoin(global_rating)
        ).where(
            login.c.id == player.id
        )
        result = await conn.execute(sql)
        row = result.fetchone()

        if row is None:
            self._logger.info("Found no ratings for Player with id %i", player.id)
            return

        row = row._mapping

        table_map = {
            RatingType.GLOBAL: "global_rating_{}",
            RatingType.LADDER_1V1: "ladder1v1_rating_{}",
        }
        for rating_type in rating_types:
            if rating_type not in table_map:
                raise ValueError(f"Unknown rating type {rating_type}.")

            table = table_map[rating_type]
            if row[table.format("mean")] is None:
                self._logger.info(
                    "Found no %s ratings for Player with id %i",
                    rating_type, player.id
                )
                continue

            player.ratings[rating_type] = (
                row[table.format("mean")],
                row[table.format("deviation")]
            )
            player.game_count[rating_type] = row[table.format("numGames")]

    def remove_player(self, player: Player):
        if player.id in self._players:
            del self._players[player.id]
            metrics.players_online.set(len(self._players))

    async def has_permission_role(self, player: Player, role_name: str) -> bool:
        async with self._db.acquire() as conn:
            result = await conn.execute(
                select([group_permission.c.id])
                .select_from(
                    user_group_assignment
                    .join(group_permission_assignment, onclause=(
                        user_group_assignment.c.group_id ==
                        group_permission_assignment.c.group_id
                    ))
                    .join(group_permission)
                )
                .where(
                    and_(
                        user_group_assignment.c.user_id == player.id,
                        group_permission.c.technical_name == role_name
                    )
                )
            )
            row = result.fetchone()
            return row is not None

    def is_uniqueid_exempt(self, user_id: int) -> bool:
        return user_id in self.uniqueid_exempt

    def get_player(self, player_id: int) -> Optional[Player]:
        return self._players.get(player_id)

    def signal_player_rating_change(
        self, player_id: int, rating_type: str, new_rating: Rating
    ) -> None:
        player = self.get_player(player_id)
        if player is None:
            self._logger.debug(
                "Received rating change for player with id %i not in PlayerService.",
                player_id
            )
            return

        self._logger.debug(
            "Received rating change for player %s.", player
        )
        player.ratings[rating_type] = new_rating
        player.game_count[rating_type] += 1
        self.mark_dirty(player)

    async def update_data(self):
        """
        Update rarely-changing data, such as the admin list and the list of users exempt from the
        uniqueid check.
        """
        async with self._db.acquire() as conn:
            # UniqueID-exempt users.
            result = await conn.execute(
                "SELECT `user_id` FROM uniqueid_exempt"
            )
            self.uniqueid_exempt = frozenset(map(lambda x: x[0], result))

    async def shutdown(self):
        for player in self:
            if player.lobby_connection is not None:
                with contextlib.suppress(Exception):
                    player.lobby_connection.write_warning(
                        "The server has been shut down for maintenance, "
                        "but should be back online soon. If you experience any "
                        "problems, please restart your client. <br/><br/>"
                        "We apologize for this interruption."
                    )

    def on_connection_lost(self, conn: "LobbyConnection") -> None:
        if not conn.player:
            return

        self.remove_player(conn.player)

        self._logger.debug(
            "Removed player %d, %s, %d",
            conn.player.id,
            conn.player.login,
            conn.session
        )
