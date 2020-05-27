import asyncio
from typing import Optional, Set, ValuesView

import aiocron
import server.metrics as metrics
from server.db import FAFDatabase
from server.decorators import with_logger
from server.players import Player
from server.rating import RatingType
from sqlalchemy import and_, select

from .core import Service
from .db.models import (
    avatars, avatars_list, clan, clan_membership, global_rating,
    group_permission, group_permission_assignment, ladder1v1_rating, login,
    user_group, user_group_assignment
)


@with_logger
class PlayerService(Service):
    def __init__(self, database: FAFDatabase):
        self._db = database
        self._players = dict()

        # Static-ish data fields.
        self.uniqueid_exempt = {}
        self.client_version_info = ('0.0.0', None)
        self._dirty_players = set()

    async def initialize(self) -> None:
        await self.update_data()
        self._update_cron = aiocron.crontab(
            '*/10 * * * *', func=self.update_data
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

    @property
    def dirty_players(self) -> Set[Player]:
        return self._dirty_players

    def mark_dirty(self, player: Player):
        self._dirty_players.add(player)

    def clear_dirty(self):
        self._dirty_players = set()

    async def fetch_player_data(self, player):
        async with self._db.acquire() as conn:
            result = await conn.execute(
                select([user_group.c.technical_name])
                .select_from(user_group_assignment.join(user_group))
                .where(user_group_assignment.c.user_id == player.id)
            )
            player.user_groups = {row.technical_name async for row in result}

            sql = select([
                avatars_list.c.url,
                avatars_list.c.tooltip,
                global_rating.c.mean,
                global_rating.c.deviation,
                global_rating.c.numGames,
                ladder1v1_rating.c.mean,
                ladder1v1_rating.c.deviation,
                ladder1v1_rating.c.numGames,
                clan.c.tag
            ], use_labels=True).select_from(
                login
                .join(global_rating)
                .join(ladder1v1_rating)
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
                return

            player.ratings[RatingType.GLOBAL] = (
                row[global_rating.c.mean],
                row[global_rating.c.deviation]
            )
            player.game_count[RatingType.GLOBAL] = row[global_rating.c.numGames]

            player.ratings[RatingType.LADDER_1V1] = (
                row[ladder1v1_rating.c.mean],
                row[ladder1v1_rating.c.deviation]
            )
            player.game_count[RatingType.LADDER_1V1] = row[ladder1v1_rating.c.numGames]

            player.clan = row.get(clan.c.tag)

            url, tooltip = (
                row.get(avatars_list.c.url), row.get(avatars_list.c.tooltip)
            )
            if url and tooltip:
                player.avatar = {"url": url, "tooltip": tooltip}

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
            row = await result.fetchone()
            return row is not None

    def is_uniqueid_exempt(self, user_id: int) -> bool:
        return user_id in self.uniqueid_exempt

    def get_player(self, player_id: int) -> Optional[Player]:
        return self._players.get(player_id)

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
