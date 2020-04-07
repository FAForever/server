import asyncio
from typing import Optional, Set, ValuesView

import aiocron
import server.metrics as metrics
from server.db import FAFDatabase
from server.decorators import with_logger
from server.players import Player
from server.rating import RatingType
from trueskill import Rating
from sqlalchemy import and_, select

from .core import Service
from .db.models import (
    avatars, avatars_list, clan, clan_membership, login
)
from .db.models import legacy_global_rating, legacy_ladder1v1_rating, leaderboard, leaderboard_rating


@with_logger
class PlayerService(Service):
    def __init__(self, database: FAFDatabase):
        self._db = database
        self._players = dict()

        # Static-ish data fields.
        self.privileged_users = {}
        self.uniqueid_exempt = {}
        self.client_version_info = ('0.0.0', None)
        self._dirty_players = set()
        self._rating_type_ids = {}

    async def initialize(self) -> None:
        await self.update_data()
        self._update_cron = aiocron.crontab(
            '*/10 * * * *', func=self.update_data
        )
        await self._load_rating_type_ids()

    async def _load_rating_type_ids(self):
        async with self._db.acquire() as conn:
            sql = select([leaderboard.c.id, leaderboard.c.technical_name])
            result = await conn.execute(sql)
            rows = await result.fetchall()

        self._rating_type_ids = {row["technical_name"]: row["id"] for row in rows}

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

    @property
    def dirty_players(self) -> Set[Player]:
        return self._dirty_players

    def mark_dirty(self, player: Player):
        self._dirty_players.add(player)

    def clear_dirty(self):
        self._dirty_players = set()

    async def fetch_player_data(self, player):
        async with self._db.acquire() as conn:
            sql = select([
                avatars_list.c.url,
                avatars_list.c.tooltip,
                clan.c.tag
            ], use_labels=True).select_from(
                login
                .outerjoin(clan_membership)
                .outerjoin(clan)
                .outerjoin(avatars, onclause=and_(
                    avatars.c.idUser == login.c.id,
                    avatars.c.selected == 1
                ))
                .outerjoin(avatars_list)
            ).where(login.c.id == player.id)  # yapf: disable

            result = await conn.execute(sql)
            row = await result.fetchone()
            if not row:
                self._logger.warning(f"Did not find data for player {player.id}")
                return

            player.clan = row.get(clan.c.tag)

            url, tooltip = (
                row.get(avatars_list.c.url), row.get(avatars_list.c.tooltip)
            )
            if url and tooltip:
                player.avatar = {"url": url, "tooltip": tooltip}

            await self._fetch_player_rating(player, RatingType.GLOBAL, conn)
            await self._fetch_player_rating(player, RatingType.LADDER_1V1, conn)


    async def _fetch_player_rating(self, player, rating_type, conn):
        rating_type_id = self._rating_type_ids.get(rating_type.value)
        if rating_type_id is None:
            self._logger.warning(f"Did not find rating type {rating_type}")
            raise ValueError(
                f"Did not find rating type {rating_type}. Make sure the service is initialized."
            )

        sql = select([leaderboard_rating]).where(
            and_(
                leaderboard_rating.c.login_id == player.id,
                leaderboard_rating.c.leaderboard_id == rating_type_id,
            )
        )

        result = await conn.execute(sql)
        row = await result.fetchone()

        if row is not None:
            player.ratings[rating_type] = (
                row[leaderboard_rating.c.mean],
                row[leaderboard_rating.c.deviation],
            )
            player.game_count[rating_type] = row[leaderboard_rating.c.total_games]
        else:
            await self._fetch_player_legacy_rating(player, rating_type, conn)

    async def _fetch_player_legacy_rating(self, player, rating_type, conn):
        if rating_type is RatingType.GLOBAL:
            table = legacy_global_rating
        elif rating_type is RatingType.LADDER_1V1:
            table = legacy_ladder1v1_rating
        else:
            self._logger.warning(f"Received ill-formed rating type {rating_type}")
            raise ValueError(f"Unknown rating type {rating_type}.")

        sql = select([table.c.mean, table.c.deviation, table.c.numGames]).where(
            table.c.id == player.id
        )
        result = await conn.execute(sql)
        row = await result.fetchone()

        if row is not None:
            player.ratings[rating_type] = (
                row[table.c.mean], row[table.c.deviation]
            )
            player.game_count[rating_type] = row[table.c.numGames]
        else:
            self._logger.warning(f"Found no rating of type {rating_type} for player {player.id}.")


    def remove_player(self, player: Player):
        if player.id in self._players:
            del self._players[player.id]
            metrics.players_online.set(len(self._players))

    def get_permission_group(self, user_id: int) -> int:
        return self.privileged_users.get(user_id, 0)

    def is_uniqueid_exempt(self, user_id: int) -> bool:
        return user_id in self.uniqueid_exempt

    def get_player(self, player_id: int) -> Optional[Player]:
        return self._players.get(player_id)

    def signal_player_rating_change(
        self, player_id: int, rating_type: RatingType, new_rating: Rating
    ) -> None:
        player = self.get_player(player_id)
        if player is None:
            self._logger.debug(
                "Received rating change for player with id %s not in PlayerService.",
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
            # Admins/mods
            result = await conn.execute(
                "SELECT `user_id`, `group` FROM lobby_admin"
            )
            rows = await result.fetchall()
            self.privileged_users = {r["user_id"]: r["group"] for r in rows}

            # UniqueID-exempt users.
            result = await conn.execute(
                "SELECT `user_id` FROM uniqueid_exempt"
            )
            rows = await result.fetchall()
            self.uniqueid_exempt = frozenset(map(lambda x: x[0], rows))

            # Client version number
            result = await conn.execute(
                "SELECT version, file FROM version_lobby ORDER BY id DESC LIMIT 1"
            )
            row = await result.fetchone()
            if row is not None:
                self.client_version_info = (row[0], row[1])

    async def shutdown(self):
        tasks = []
        for player in self:
            if player.lobby_connection is not None:
                tasks.append(
                    player.lobby_connection.send_warning(
                        "The server has been shut down for maintenance, "
                        "but should be back online soon. If you experience any "
                        "problems, please restart your client. <br/><br/>"
                        "We apologize for this interruption."
                    )
                )

        for fut in asyncio.as_completed(tasks):
            try:
                await fut
            except Exception as ex:
                self._logger.debug(
                    "Could not send shutdown message to %s: %s", player, ex
                )
