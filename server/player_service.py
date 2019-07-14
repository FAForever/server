import asyncio
from typing import Optional, Set

import aiocron
import server.db as db
from server.decorators import with_logger
from server.players import Player
from sqlalchemy import and_, select

from .db.models import (avatars, avatars_list, clan, clan_membership,
                        global_rating, ladder1v1_rating, login)


@with_logger
class PlayerService:
    def __init__(self):
        self.players = dict()

        # Static-ish data fields.
        self.privileged_users = {}
        self.uniqueid_exempt = {}
        self.client_version_info = ('0.0.0', None)
        self._dirty_players = set()

        asyncio.get_event_loop().run_until_complete(asyncio.ensure_future(self.update_data()))
        self._update_cron = aiocron.crontab('*/10 * * * *', func=self.update_data)

    def __len__(self):
        return len(self.players)

    def __iter__(self):
        return self.players.values().__iter__()

    def __getitem__(self, player_id: int) -> Optional[Player]:
        return self.players.get(player_id)

    def __setitem__(self, player_id: int, player: Player):
        self.players[player_id] = player

    @property
    def dirty_players(self) -> Set[Player]:
        return self._dirty_players

    def mark_dirty(self, player: Player):
        self._dirty_players.add(player)

    def clear_dirty(self):
        self._dirty_players = set()

    async def fetch_player_data(self, player):
        async with db.engine.acquire() as conn:
            sql = select([
                avatars_list.c.url,
                avatars_list.c.tooltip,
                global_rating.c.mean,
                global_rating.c.deviation,
                global_rating.c.numGames,
                ladder1v1_rating.c.mean,
                ladder1v1_rating.c.deviation,
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
            ).where(login.c.id == player.id)

            result = await conn.execute(sql)
            row = await result.fetchone()
            if not row:
                return

            player.global_rating = (
                row[global_rating.c.mean],
                row[global_rating.c.deviation]
            )
            player.numGames = row[global_rating.c.numGames]

            player.ladder_rating = (
                row[ladder1v1_rating.c.mean],
                row[ladder1v1_rating.c.deviation]
            )

            player.clan = row.get(clan.c.tag)

            url, tooltip = row.get(avatars_list.c.url), row.get(avatars_list.c.tooltip)
            if url and tooltip:
                player.avatar = {"url": url, "tooltip": tooltip}

    def remove_player(self, player: Player):
        if player.id in self.players:
            del self.players[player.id]

    def get_permission_group(self, user_id: int) -> int:
        return self.privileged_users.get(user_id, 0)

    def is_uniqueid_exempt(self, user_id: int) -> bool:
        return user_id in self.uniqueid_exempt

    def get_player(self, player_id: int) -> Optional[Player]:
        return self.players.get(player_id)

    async def update_data(self):
        """
        Update rarely-changing data, such as the admin list and the list of users exempt from the
        uniqueid check.
        """
        async with db.engine.acquire() as conn:
            # Admins/mods
            result = await conn.execute("SELECT `user_id`, `group` FROM lobby_admin")
            rows = await result.fetchall()
            self.privileged_users = dict(map(lambda r: (r[0], r[1]), rows))

            # UniqueID-exempt users.
            result = await conn.execute("SELECT `user_id` FROM uniqueid_exempt")
            rows = await result.fetchall()
            self.uniqueid_exempt = frozenset(map(lambda x: x[0], rows))

            # Client version number
            result = await conn.execute("SELECT version, file FROM version_lobby ORDER BY id DESC LIMIT 1")
            row = await result.fetchone()
            if row is not None:
                self.client_version_info = (row[0], row[1])

    def broadcast_shutdown(self):
        for player in self:
            try:
                if player.lobby_connection:
                    player.lobby_connection.send_warning(
                        "The server has been shut down for maintenance, "
                        "but should be back online soon. "
                        "If you experience any problems, please restart your client. "
                        "<br/><br/>We apologize for this interruption.")
            except Exception as ex:
                self._logger.debug("Could not send shutdown message to %s: %s".format(player, ex))
