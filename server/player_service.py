import aiomysql
import asyncio


class PlayerService(object):
    def __init__(self, db_pool: aiomysql.Pool):
        self.players = []
        self.logins = []
        self.db_pool = db_pool

    def __len__(self):
        return len(self.players)

    def __iter__(self):
        return self.players.__iter__()

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
            yield from cur.execute(
                "SELECT `clan_tag` "
                "FROM `fafclans`.`clan_tags` "
                "LEFT JOIN `fafclans`.players_list "
                "ON `fafclans`.players_list.player_id = `fafclans`.`clan_tags`.player_id "
                "WHERE `faf_id` = %s", player.id)
            player.clan = yield from cur.fetchone()

    def addUser(self, newplayer):
        gamesocket = None
        lobbySocket = None
        # login not in current active players
        if not newplayer.getLogin() in self.logins:
            self.logins.append(newplayer.getLogin())
            self.players.append(newplayer)
            return gamesocket, lobbySocket
        else:
            # login in current active player list !

            for player in self.players:
                if newplayer.session == player.session:
                    # uuid is the same, I don't know how it's possible, but we do nothing.
                    return gamesocket, lobbySocket

                if newplayer.getLogin() == player.getLogin():
                    # login exists, uuid not the same
                    try:
                        lobbyThread = player.lobbyThread
                        if lobbyThread is not None:
                            lobbySocket = lobbyThread.socket
                    except:
                        pass

                    self.players.append(newplayer)
                    self.logins.append(newplayer.login)

                    return gamesocket, lobbySocket

    def remove_player(self, player):
        if player.login in self.logins:
            self.logins.remove(player.login)
            if player in self.players:
                self.players.remove(player)
                # del player
            return 1
        else:
            return 0

    def findByName(self, name):
        for player in self.players:
            if player.getLogin() == name:
                return player
        return 0

    def findByIp(self, ip):
        """
        Look up a user by IP
        :param ip:
        :rtype: Player
        """
        for player in self.players:
            if player.ip == ip and player.game is not None:
                return player
        return None

    def find_by_ip_and_session(self, ip, session):
        for player in self.players:
            if player.ip == ip and player.session == session and player.game is not None:
                return player
        return None
