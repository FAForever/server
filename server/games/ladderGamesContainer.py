import random


from PySide.QtSql import QSqlQuery
import asyncio
import trueskill
import config

from .gamesContainer import  GamesContainer
from .ladderGame import Ladder1V1Game
import server
from server.players import Player, PlayerState
import server.db as db


class Ladder1V1GamesContainer(GamesContainer):
    """Class for 1vs1 ladder games"""
    listable = False

    def __init__(self, db, games_service, desc, name='ladder1v1', nice_name='ladder 1 vs 1'):
        super(Ladder1V1GamesContainer, self).__init__(name, desc, nice_name, db, games_service)

        self.players = []
        self.host = False
        self.join = False
        self.games_service = games_service

    @asyncio.coroutine
    def getLeague(self, season, player):
        with (yield from db.db_pool) as conn:
            with (yield from conn.cursor()) as cursor:
                yield from cursor.execute("SELECT league FROM %s WHERE idUser = %s", (season, player.id))
                (league, ) = yield from cursor.fetchone()
                if league:
                    return league

    @asyncio.coroutine
    def addPlayer(self, player):
        if player not in self.players:
            league = yield from self.getLeague(config.LADDER_SEASON, player)
            if not league:
                with (yield from db.db_pool) as conn:
                    with (yield from conn.cursor()) as cursor:
                        yield from cursor.execute("INSERT INTO %s (`idUser` ,`league` ,`score`) "
                                                  "VALUES (%s, 1, 0)", (config.LADDER_SEASON, player.id))

            player.league = league

            self.players.append(player)
            player.state = PlayerState.SEARCHING_LADDER
            mean, deviation = player.ladder_rating

            if deviation > 490:
                player.lobbyThread.sendJSON(dict(command="notice", style="info", text="<i>Welcome to the matchmaker system.</i><br><br><b>You will be randomnly matched until the system learn and know enough about you.</b><br>After that, you will be only matched against someone of your level.<br><br><b>So don't worry if your first games are uneven, this will get better over time !</b>"))
            elif deviation > 250:
                progress = (500.0 - deviation) / 2.5
                player.lobbyThread.sendJSON(dict(command="notice", style="info", text="The system is still learning you. <b><br><br>The learning phase is " + str(progress)+"% complete<b>"))
            
            return 1
        return 0
    
    def getMatchQuality(self, player1: Player, player2: Player):
        return trueskill.quality_1vs1(player1.ladder_rating, player2.ladder_rating)

    @asyncio.coroutine
    def startGame(self, player1, player2):
        player1.state = PlayerState.HOSTING
        player2.state = PlayerState.JOINING

        (mapId, mapName) = random.choice(self.games_service.ladder_maps)

        ngame = Ladder1V1Game(self.games_service.createUuid(), self, self.game_service)
        ngame.game_mode = self.game_mode
        id = ngame.id

        player1.game = id
        player2.game = id

        # Host is player 1
        ngame.setGameMap(mapName)
        
        ngame.host = player1
        ngame.name = str(player1.login + " Vs " + player2.login)

        ngame.set_player_option(player1.id, 'StartSpot', 1)
        ngame.set_player_option(player2.id, 'StartSpot', 2)
        ngame.set_player_option(player1.id, 'Team', 1)
        ngame.set_player_option(player2.id, 'Team', 2)

        ngame.addPlayerToJoin(player2)

        ngame.setLeaguePlayer(player1)
        ngame.setLeaguePlayer(player2)

        # player 2 will be in game
        
        self.addGame(ngame)

        #warn both players
        json = {
            "command": "game_launch",
            "mod": self.game_mode,
            "mapname": str(map),
            "reason": "ranked",
            "uid": id,
            "args": ["/players 2", "/team 1"]
        }

        player1.lobbyThread.sendJSON(json)
