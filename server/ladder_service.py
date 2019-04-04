import asyncio
import random
from typing import List, NamedTuple

from sqlalchemy import and_, func, select, text

from . import db
from .config import LADDER_ANTI_REPETITION_LIMIT
from .db.models import game_featuredMods, game_player_stats, game_stats
from .decorators import with_logger
from .players import Player, PlayerState

MapDescription = NamedTuple('Map', [("id", int), ("name", str), ("path", str)])


@with_logger
class LadderService:
    """
    Service responsible for managing the 1v1 ladder. Does matchmaking, updates statistics, and
    launches the games.
    """
    def __init__(self, games_service: "GameService"):
        self._informed_players = []
        self.game_service = games_service

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

    async def start_game(self, host: Player, guest: Player):
        host.state = PlayerState.HOSTING
        guest.state = PlayerState.JOINING

        (map_id, map_name, map_path) = await self.choose_map([host, guest])

        game = self.game_service.create_game(
            game_mode='ladder1v1',
            host=host,
            name=f"{host.login} Vs {guest.login}"
        )

        host.game = game
        guest.game = game

        game.map_file_path = map_path

        game.set_player_option(host.id, 'StartSpot', 1)
        game.set_player_option(guest.id, 'StartSpot', 2)
        game.set_player_option(host.id, 'Faction', host.faction)
        game.set_player_option(guest.id, 'Faction', guest.faction)
        game.set_player_option(host.id, 'Color', 1)
        game.set_player_option(guest.id, 'Color', 2)
        game.set_player_option(host.id, 'Army', 2)
        game.set_player_option(guest.id, 'Army', 3)

        # Remembering that "Team 1" corresponds to "-": the non-team.
        game.set_player_option(host.id, 'Team', 1)
        game.set_player_option(guest.id, 'Team', 1)

        mapname = map_path[5:-4]  # FIXME: Database filenames contain the maps/ prefix and .zip suffix.
                                  # Really in the future, just send a better description
        host.lobby_connection.launch_game(game, host.game_port, is_host=True, use_map=mapname)
        await asyncio.sleep(4)
        guest.lobby_connection.launch_game(game, guest.game_port, is_host=False, use_map=mapname)

    async def choose_map(self, players: [Player]) -> MapDescription:
        maps = self.game_service.ladder_maps

        if not maps:
            self._logger.error("Trying to choose a map from an empty map pool!")
            raise RuntimeError("Ladder maps not set!")

        recently_played_map_ids = {
            map_id for player in players for map_id in
            await self.get_ladder_history(player, limit=LADDER_ANTI_REPETITION_LIMIT)
        }
        randomized_maps = random.sample(maps, len(maps))

        try:
            return next(
                filter(
                    lambda m: m[0] not in recently_played_map_ids,
                    randomized_maps
                )
            )
        except StopIteration:
            # If all maps were played recently, pick a random one
            return randomized_maps[0]

    async def get_ladder_history(self, player: Player, limit=3) -> List[int]:
        async with db.engine.acquire() as conn:
            query = select([
                game_stats.c.mapId,
            ]).select_from(
                game_player_stats.join(game_stats).join(game_featuredMods)
            ).where(
                and_(
                    game_player_stats.c.playerId == player.id,
                    game_stats.c.startTime >= func.now() - text("interval 1 day"),
                    game_featuredMods.c.gamemod == "ladder1v1"
                )
            ).order_by(game_stats.c.startTime.desc()).limit(limit)

            # Collect all the rows from the ResultProxy
            return [row[game_stats.c.mapId] async for row in await conn.execute(query)]
