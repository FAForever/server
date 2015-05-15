class PlayerService(object):
    def __init__(self):
        self.players = []
        self.logins = []

    def __len__(self):
        return len(self.players)

    def __iter__(self):
        return self.players.__iter__()

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
                #del player
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
