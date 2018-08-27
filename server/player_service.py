import aiomysql
import asyncio
import aiocron
import marisa_trie
import pymysql

from server.decorators import with_logger
from server.players import Player


@with_logger
class PlayerService:
    def __init__(self, db_pool: aiomysql.Pool):
        self.players = dict()
        self.db_pool = db_pool

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

    def __getitem__(self, item) -> Player:
        return self.players.get(item)

    def __setitem__(self, key, value):
        self.players[key] = value

    @property
    def dirty_players(self):
        return self._dirty_players

    def mark_dirty(self, player):
        self._dirty_players.add(player)

    def clear_dirty(self):
        self._dirty_players = set()

    @asyncio.coroutine
    def fetch_player_data(self, player):
        with (yield from self.db_pool) as conn:
            cur = yield from conn.cursor()
            yield from cur.execute('SELECT mean, deviation, numGames FROM `global_rating` '
                                   'WHERE id=%s', player.id)
            result = yield from cur.fetchone()
            if not result:
                result = (1500, 500, 0)
            (mean, dev, num_games) = result
            player.global_rating = (mean, dev)
            player.numGames = num_games
            yield from cur.execute('SELECT mean, deviation FROM `ladder1v1_rating` '
                                   'WHERE id=%s', player.id)
            player.ladder_rating = yield from cur.fetchone()

            ## Clan informations
            try:
                yield from cur.execute(
                    "SELECT tag "
                    "FROM login "
                    "JOIN clan_membership "
                    "ON login.id = clan_membership.player_id "
                    "JOIN clan ON clan_membership.clan_id = clan.id "
                    "where player_id =  %s", player.id)
                result = yield from cur.fetchone()
                if result:
                    (player.clan, ) = result
            except (pymysql.ProgrammingError, pymysql.OperationalError):
                pass

    def remove_player(self, player):
        if player.id in self.players:
            del self.players[player.id]

    def get_permission_group(self, user_id):
        return self.privileged_users.get(user_id, 0)

    def is_uniqueid_exempt(self, user_id):
        return user_id in self.uniqueid_exempt

    def has_blacklisted_domain(self, email):
        # A valid email only has one @ anyway.
        domain = email.split("@")[1]
        return domain in self.blacklisted_email_domains

    def get_player(self, player_id):
        if player_id in self.players:
            return self.players[player_id]

    async def update_data(self):
        """
        Update rarely-changing data, such as the admin list and the list of users exempt from the
        uniqueid check.
        """
        async with self.db_pool.get() as conn:
            cursor = await conn.cursor()

            # Admins/mods
            await cursor.execute("SELECT `user_id`, `group` FROM lobby_admin")
            rows = await cursor.fetchall()
            self.privileged_users = dict(rows)

            # UniqueID-exempt users.
            await cursor.execute("SELECT `user_id` FROM uniqueid_exempt")
            rows = await cursor.fetchall()
            self.uniqueid_exempt = frozenset(map(lambda x: x[0], rows))

            # Client version number
            await cursor.execute("SELECT version, file FROM version_lobby ORDER BY id DESC LIMIT 1")
            result = await cursor.fetchone()
            
            if not (result is None):
                self.client_version_info = result

            # Blacklisted email domains (we don't like disposable email)
            await cursor.execute("SELECT domain FROM email_domain_blacklist")
            rows = await cursor.fetchall()
            # Get list of reversed blacklisted domains (so we can (pre)suffix-match incoming emails
            # in sublinear time)
            self.blacklisted_email_domains = marisa_trie.Trie(map(lambda x: x[0], rows))

    def broadcast_shutdown(self):
        for player in self:
            try:
                if player.lobby_connection:
                    player.lobby_connection.send_warning("""
                    The server has been shut down for maintenance, but should be back online soon. If you experience any
                    problems, please restart your client.<br><br>We apologize for this interruption.""")
            except Exception as ex:
                self._logger.debug("Could not send shutdown message to %s: %s".format(player, ex))
