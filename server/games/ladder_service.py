import random


import asyncio
import trueskill
import config

from .ladder_game import LadderGame
from server.players import Player, PlayerState
import server.db as db


class LadderService:
    """Class for 1vs1 ladder games"""
    listable = False

    def __init__(self, games_service, desc, name='ladder1v1', nice_name='ladder 1 vs 1'):
        self.players = []
        self.game_service = games_service

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
                player.lobby_connection.sendJSON(dict(command="notice", style="info", text="<i>Welcome to the matchmaker system.</i><br><br><b>You will be randomnly matched until the system learn and know enough about you.</b><br>After that, you will be only matched against someone of your level.<br><br><b>So don't worry if your first games are uneven, this will get better over time !</b>"))
            elif deviation > 250:
                progress = (500.0 - deviation) / 2.5
                player.lobby_connection.sendJSON(dict(command="notice", style="info", text="The system is still learning you. <b><br><br>The learning phase is " + str(progress)+"% complete<b>"))
            
            return 1
        return 0
    
    def getMatchQuality(self, player1: Player, player2: Player):
        return trueskill.quality_1vs1(player1.ladder_rating, player2.ladder_rating)

    @asyncio.coroutine
    def startGame(self, player1, player2):
        player1.state = PlayerState.HOSTING
        player2.state = PlayerState.JOINING

        (map_id, map_path) = random.choice(self.game_service.ladder_maps)

        game = LadderGame(self.game_service.createUuid(), self.game_service)

        player1.game = game
        player2.game = game

        game.map_file_path = map_path

        # Host is player 1
        game.host = player1
        game.name = str(player1.login + " Vs " + player2.login)

        game.set_player_option(player1.id, 'StartSpot', 1)
        game.set_player_option(player2.id, 'StartSpot', 2)

        # Remembering that "Team 1" corresponds to "-": the non-team.
        game.set_player_option(player1.id, 'Team', 2)
        game.set_player_option(player2.id, 'Team', 3)

        game.setLeaguePlayer(player1)
        game.setLeaguePlayer(player2)

        # player 2 will be in game
        
        #warn both players
        json = {
            "command": "game_launch",
            "mod": game.game_mode,
            "mapname": map_path,
            "mapid": map_id,
            "reason": "ranked",
            "uid": game.id,
            "args": ["/players 2", "/team 1"]
        }

        player1.lobby_connection.sendJSON(json)

