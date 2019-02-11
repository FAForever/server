import asyncio
from typing import Optional, Set

import aiocron
import marisa_trie
import pymysql
import server.db as db
from server.decorators import with_logger
from server.players import Player


@with_logger
class PlayerService:
    def __init__(self):
        self.players = dict()

        # Static-ish data fields.
        self.privileged_users = {}
        self.uniqueid_exempt = {}
        self.client_version_info = ('0.0.0', None)
        self.blacklisted_email_domains = {}
        self._dirty_players = set()

        self.ladder_queue = None
        asyncio.get_event_loop().run_until_complete(asyncio.async(self.update_data()))
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
            result = await conn.execute(
                'SELECT mean, deviation, numGames FROM `global_rating` '
                'WHERE id=%s', player.id)
            row = await result.fetchone()
            if not row:
                (mean, dev, num_games) = (1500, 500, 0)
            (mean, dev, num_games) = row[0], row[1], row[2]
            player.global_rating = (mean, dev)
            player.numGames = num_games
            result = await conn.execute(
                'SELECT mean, deviation FROM `ladder1v1_rating` '
                'WHERE id=%s', player.id)
            row = await result.fetchone()
            player.ladder_rating = (row[0], row[1])

            ## Clan informations
            try:
                result = await conn.execute(
                    "SELECT tag "
                    "FROM login "
                    "JOIN clan_membership "
                    "ON login.id = clan_membership.player_id "
                    "JOIN clan ON clan_membership.clan_id = clan.id "
                    "where player_id =  %s", player.id)
                row = await result.fetchone()
                if row:
                    player.clan = row[0]
            except (pymysql.ProgrammingError, pymysql.OperationalError):
                pass

    def remove_player(self, player: Player):
        if player.id in self.players:
            del self.players[player.id]

    def get_permission_group(self, user_id: int):
        return self.privileged_users.get(user_id, 0)

    def is_uniqueid_exempt(self, user_id):
        return user_id in self.uniqueid_exempt

    def has_blacklisted_domain(self, email: str) -> bool:
        # A valid email only has one @ anyway.
        domain = email.split("@")[1]
        return domain in self.blacklisted_email_domains

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

            # Blacklisted email domains (we don't like disposable email)
            result = await conn.execute("SELECT domain FROM email_domain_blacklist")
            # Get list of reversed blacklisted domains (so we can (pre)suffix-match incoming emails
            # in sublinear time)
            rows = await result.fetchall()
            self.blacklisted_email_domains = marisa_trie.Trie(map(lambda x: x[0], rows))

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
