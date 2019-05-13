import asyncio
import random
from collections import defaultdict
from typing import Dict, List, NamedTuple, Set

from sqlalchemy import and_, func, select, text

from . import db
from .config import LADDER_ANTI_REPETITION_LIMIT
from .db.models import game_featuredMods, game_player_stats, game_stats
from .decorators import with_logger
from .game_service import GameService
from .matchmaker import MatchmakerQueue, Search
from .players import Player, PlayerState

MapDescription = NamedTuple('Map', [("id", int), ("name", str), ("path", str)])


@with_logger
class LadderService:
    """
    Service responsible for managing the 1v1 ladder. Does matchmaking, updates statistics, and
    launches the games.
    """
    def __init__(self, games_service: GameService):
        self._informed_players: Set[Player] = set()
        self.game_service = games_service

        # Hardcoded here until it needs to be dynamic
        self.queues = {
            'ladder1v1': MatchmakerQueue('ladder1v1', game_service=games_service)
        }

        self.searches: Dict[str, Dict[Player, Search]] = defaultdict(dict)

        asyncio.ensure_future(self.handle_queue_matches())

    def start_search(self, initiator: Player, search: Search, queue_name: str):
        self._cancel_existing_searches(initiator)

        for player in search.players:
            player.state = PlayerState.SEARCHING_LADDER

            # For now, inform_player is only designed for ladder1v1
            if queue_name == "ladder1v1":
                self.inform_player(player)

        self.searches[queue_name][initiator] = search

        self._logger.info("%s is searching for '%s': %s", initiator, queue_name, search)

        asyncio.ensure_future(self.queues[queue_name].search(search))

    def cancel_search(self, initiator: Player):
        searches = self._cancel_existing_searches(initiator)

        for search in searches:
            for player in search.players:
                if player.state == PlayerState.SEARCHING_LADDER:
                    player.state = PlayerState.IDLE
            self._logger.info("%s stopped searching for ladder: %s", player, search)

    def _cancel_existing_searches(self, initiator: Player) -> List[Search]:
        searches = []
        for queue_name in self.queues:
            search = self.searches[queue_name].get(initiator)
            if search:
                search.cancel()
                searches.append(search)
                del self.searches[queue_name][initiator]
        return searches

    def inform_player(self, player: Player):
        if player not in self._informed_players:
            self._informed_players.add(player)
            mean, deviation = player.ladder_rating

            if deviation > 490:
                player.lobby_connection.sendJSON(dict(command="notice", style="info", text="<i>Welcome to the matchmaker</i><br><br><b>Until you've played enough games for the system to learn your skill level, you'll be matched randomly.</b><br>Afterwards, you'll be more reliably matched up with people of your skill level: so don't worry if your first few games are uneven. This will improve as you play!</b>"))
            elif deviation > 250:
                progress = (500.0 - deviation) / 2.5
                player.lobby_connection.sendJSON(dict(command="notice", style="info", text="The system is still learning you. <b><br><br>The learning phase is " + str(progress)+"% complete<b>"))

    async def handle_queue_matches(self):
        async for s1, s2 in self.queues["ladder1v1"].iter_matches():
            assert len(s1.players) == 1
            assert len(s2.players) == 1
            p1, p2 = s1.players[0], s2.players[0]
            msg = {
                "command": "match_found",
                "queue": "ladder1v1"
            }
            p1.lobby_connection.send(msg)
            p2.lobby_connection.send(msg)
            asyncio.ensure_future(self.start_game(p1, p2))

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
        host.lobby_connection.launch_game(game, is_host=True, use_map=mapname)
        try:
            hosted = await game.await_hosted()
            if not hosted:
                raise TimeoutError("Host left lobby")
        except TimeoutError:
            msg = {"command": "game_launch_timeout"}
            host.lobby_connection.send(msg)
            guest.lobby_connection.send(msg)
            # TODO: Uncomment this line once the client supports `game_launch_timeout`.
            # Until then, returning here will cause the client to think it is
            # searching for ladder, even though the server has already removed it
            # from the queue.
            # return

        guest.lobby_connection.launch_game(game, is_host=False, use_map=mapname)

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

    def on_connection_lost(self, player):
        self.cancel_search(player)
        if player in self._informed_players:
            self._informed_players.remove(player)

    def shutdown_queues(self):
        for queue in self.queues.values():
            queue.shutdown()
