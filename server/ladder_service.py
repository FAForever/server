import random
import asyncio

from server.games.ladder_game import LadderGame
from server.players import PlayerState


class LadderService:
    """
    Service responsible for managing the 1v1 ladder. Does matchmaking, updates statistics, and
    launches the games.
    """
    def __init__(self, games_service, game_stats_service):
        self._informed_players = []
        self.game_service = games_service
        self.game_stats_service = game_stats_service

    def inform_player(self, player):
        if player not in self._informed_players:
            self._informed_players.append(player)
            player.state = PlayerState.SEARCHING_LADDER
            mean, deviation = player.ladder_rating

            if deviation > 490:
                player.lobby_connection.sendJSON(dict(command="notice", style="info", text="<i>Welcome to the matchmaker</i><br><br><b>Until you've played enough games for the system to learn your skill level, you'll be matched randomly.</b><br>Afterwards, you'll be more reliably matched up with people of your skill level: so don't worry if your first few games are uneven. This will improve as you play!</b>"))
            elif deviation > 250:
                progress = (500.0 - deviation) / 2.5
                player.lobby_connection.sendJSON(dict(command="notice", style="info", text="The system is still learning you. <b><br><br>The learning phase is " + str(progress)+"% complete<b>"))

    async def start_game(self, player1, player2):
        player1.state = PlayerState.HOSTING
        player2.state = PlayerState.JOINING

        (map_id, map_name, map_path) = random.choice(self.game_service.ladder_maps)

        game = LadderGame(self.game_service.createUuid(), self.game_service, self.game_stats_service)
        self.game_service.games[game.id] = game

        player1.game = game
        player2.game = game

        game.map_file_path = map_path

        # Host is player 1
        game.host = player1
        game.name = str(player1.login + " Vs " + player2.login)

        game.set_player_option(player1.id, 'StartSpot', 1)
        game.set_player_option(player2.id, 'StartSpot', 2)
        game.set_player_option(player1.id, 'Faction', player1.faction)
        game.set_player_option(player2.id, 'Faction', player2.faction)
        game.set_player_option(player1.id, 'Color', 1)
        game.set_player_option(player2.id, 'Color', 2)
        game.set_player_option(player1.id, 'Army', 2)
        game.set_player_option(player2.id, 'Army', 3)

        # Remembering that "Team 1" corresponds to "-": the non-team.
        game.set_player_option(player1.id, 'Team', 1)
        game.set_player_option(player2.id, 'Team', 1)

        mapname = map_path[5:-4]  # FIXME: Database filenames contain the maps/ prefix and .zip suffix.
                                  # Really in the future, just send a better description
        player1.lobby_connection.launch_game(game, is_host=True, use_map=mapname)
        await asyncio.sleep(4)
        player2.lobby_connection.launch_game(game, is_host=False, use_map=mapname)
