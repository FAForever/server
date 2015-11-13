import aiomysql
import asyncio
import aiocron
import marisa_trie
import pymysql
from server.matchmaker import MatchmakerQueue


class PlayerService:
    def __init__(self, db_pool: aiomysql.Pool):
        self.players = dict()
        self.db_pool = db_pool

        # Static-ish data fields.
        self.privileged_users = {}
        self.uniqueid_exempt = {}
        self.client_version_info = ('0.0.0', None)
        self.blacklisted_email_domains = {}

        self.ladder_queue = MatchmakerQueue('ladder1v1', self)
        asyncio.get_event_loop().run_until_complete(asyncio.async(self.really_update_static_ish_data()))

    def __len__(self):
        return len(self.players)

    def __iter__(self):
        return self.players.values().__iter__()

    def __getitem__(self, item):
        return self.players[item]

    def __setitem__(self, key, value):
        self.players[key] = value

    @asyncio.coroutine
    def update_rating(self, player, rating='global'):
        """
        Update the given rating for the given player

        :param Player player: the player to update
        :param rating: 'global' or 'ladder1v1'
        :param new_rating: New rating, if None, fetches the rating from the database
        """
        with (yield from self.db_pool) as conn:
            cursor = yield from conn.cursor()
            if rating == 'global':
                mean, deviation = player.global_rating
            else:
                mean, deviation = player.ladder_rating
            yield from cursor.execute('UPDATE `{}_rating` '
                                      'SET mean=%s, deviation=%s '
                                      'WHERE id=%s', (mean, deviation, player.id))

    @asyncio.coroutine
    def fetch_player_data(self, player):
        with (yield from self.db_pool) as conn:
            cur = yield from conn.cursor()
            yield from cur.execute('SELECT mean, deviation, numGames FROM `global_rating` '
                                   'WHERE id=%s', player.id)
            (mean, dev, num_games) = yield from cur.fetchone()
            player.global_rating = (mean, dev)
            player.numGames = num_games
            yield from cur.execute('SELECT mean, deviation FROM `ladder1v1_rating` '
                                   'WHERE id=%s', player.id)
            player.ladder_rating = yield from cur.fetchone()

            ## Clan informations
            try:
                yield from cur.execute(
                    "SELECT `clan_tag` "
                    "FROM `fafclans`.`clan_tags` "
                    "LEFT JOIN `fafclans`.players_list "
                    "ON `fafclans`.players_list.player_id = `fafclans`.`clan_tags`.player_id "
                    "WHERE `faf_id` = %s", player.id)
                (player.clan, _) = yield from cur.fetchone()
            except (pymysql.ProgrammingError, pymysql.OperationalError):
                pass

    def remove_player(self, player):
        del self.players[player.id]

    def get_permission_group(self, user_id):
        return self.privileged_users.get(user_id, 0)

    def is_uniqueid_exempt(self, user_id):
        return user_id in self.uniqueid_exempt

    def has_blacklisted_domain(self, email):
        return len(self.blacklisted_email_domains.keys(email[::-1])) != 0

    def get_player(self, player_id):
        if player_id in self.players:
            return self.players[player_id]

    @asyncio.coroutine
    def really_update_static_ish_data(self):
        """
        Update rarely-changing data, such as the admin list and the list of users exempt from the
        uniqueid check.
        """
        with (yield from self.db_pool) as conn:
            cursor = yield from conn.cursor()

            # Admins/mods
            yield from cursor.execute("SELECT `user_id`, `group` FROM lobby_admin")
            rows = yield from cursor.fetchall()
            self.privileged_users = dict(rows)

            # UniqueID-exempt users.
            yield from cursor.execute("SELECT `user_id` FROM uniqueid_exempt")
            rows = yield from cursor.fetchall()
            self.uniqueid_exempt = frozenset(map(lambda x: x[0], rows))

            # Client version number
            yield from cursor.execute("SELECT version, file FROM version_lobby ORDER BY id DESC LIMIT 1")
            self.client_version_info = yield from cursor.fetchone()

            # Blacklisted email domains (we don't like disposable email)
            yield from cursor.execute("SELECT domain FROM email_domain_blacklist")
            rows = yield from cursor.fetchall()
            # Get list of reversed blacklisted domains (so we can (pre)suffix-match incoming emails
            # in sublinear time)
            self.blacklisted_email_domains = marisa_trie.Trie(map(lambda x: x[0][::-1], rows))

    @aiocron.crontab('0 * * * *')
    @asyncio.coroutine
    def update_static_ish_data(self):
        self.really_update_static_ish_data()
