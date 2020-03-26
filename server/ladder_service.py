import asyncio
import contextlib
import random
from collections import defaultdict
from typing import Dict, List, NamedTuple, Set

from server.db import FAFDatabase
from server.rating import RatingType
from sqlalchemy import and_, func, select, text

from .async_functions import gather_without_exceptions
from .config import LADDER_ANTI_REPETITION_LIMIT
from .core import Service
from .db.models import game_featuredMods, game_player_stats, game_stats
from .decorators import with_logger
from .game_service import GameService
from .matchmaker import MatchmakerQueue, Search
from .players import Player, PlayerState
from .protocol import DisconnectedError
from .types import GameLaunchOptions

MapDescription = NamedTuple('Map', [("id", int), ("name", str), ("path", str)])


@with_logger
class LadderService(Service):
    """
    Service responsible for managing the 1v1 ladder. Does matchmaking, updates
    statistics, and launches the games.
    """
    def __init__(
        self,
        database: FAFDatabase,
        game_service: GameService,
    ):
        self._db = database
        self._informed_players: Set[Player] = set()
        self.game_service = game_service

        # Hardcoded here until it needs to be dynamic
        self.queues = {
            'ladder1v1': MatchmakerQueue('ladder1v1', game_service)
        }

        self.searches: Dict[str, Dict[Player, Search]] = defaultdict(dict)

    async def initialize(self) -> None:
        await asyncio.gather(*[
            queue.initialize() for queue in self.queues.values()
        ])
        asyncio.create_task(self.handle_queue_matches())

    async def start_search(self, initiator: Player, search: Search, queue_name: str):
        # TODO: Consider what happens if players disconnect while starting
        # search. Will need a message to inform other players in the search
        # that it has been cancelled.
        self._cancel_existing_searches(initiator)

        tasks = []
        for player in search.players:
            player.state = PlayerState.SEARCHING_LADDER

            # For now, inform_player is only designed for ladder1v1
            if queue_name == "ladder1v1":
                tasks.append(self.inform_player(player))

        try:
            await asyncio.gather(*tasks)
        except DisconnectedError:
            self._logger.info(
                "%i failed to start %s search due to a disconnect: %s",
                initiator, queue_name, search
            )
            await self.cancel_search(initiator)

        self.searches[queue_name][initiator] = search

        self._logger.info(
            "%s is searching for '%s': %s", initiator, queue_name, search
        )

        asyncio.create_task(self.queues[queue_name].search(search))

    async def cancel_search(self, initiator: Player):
        searches = self._cancel_existing_searches(initiator)

        tasks = []
        for search in searches:
            for player in search.players:
                if player.state == PlayerState.SEARCHING_LADDER:
                    player.state = PlayerState.IDLE

                if player.lobby_connection is not None:
                    tasks.append(player.send_message({
                        "command": "game_matchmaking",
                        "state": "stop"
                    }))
            self._logger.info(
                "%s stopped searching for ladder: %s", player, search
            )

        await gather_without_exceptions(tasks, DisconnectedError)

    def _cancel_existing_searches(self, initiator: Player) -> List[Search]:
        searches = []
        for queue_name in self.queues:
            search = self.searches[queue_name].get(initiator)
            if search:
                search.cancel()
                searches.append(search)
                del self.searches[queue_name][initiator]
        return searches

    async def inform_player(self, player: Player):
        if player not in self._informed_players:
            self._informed_players.add(player)
            mean, deviation = player.ratings[RatingType.LADDER_1V1]

            if deviation > 490:
                await player.send_message({
                    "command": "notice",
                    "style": "info",
                    "text": (
                        "<i>Welcome to the matchmaker</i><br><br><b>Until "
                        "you've played enough games for the system to learn "
                        "your skill level, you'll be matched randomly.</b><br>"
                        "Afterwards, you'll be more reliably matched up with "
                        "people of your skill level: so don't worry if your "
                        "first few games are uneven. This will improve as you "
                        "play!</b>"
                    )
                })
            elif deviation > 250:
                progress = (500.0 - deviation) / 2.5
                await player.send_message({
                    "command": "notice",
                    "style": "info",
                    "text": (
                        "The system is still learning you.<b><br><br>The "
                        f"learning phase is {progress}% complete<b>"
                    )
                })

    async def handle_queue_matches(self):
        async for s1, s2 in self.queues["ladder1v1"].iter_matches():
            try:
                assert len(s1.players) == 1
                assert len(s2.players) == 1
                p1, p2 = s1.players[0], s2.players[0]
                msg = {"command": "match_found", "queue": "ladder1v1"}
                # TODO: Handle disconnection with a client supported message
                await asyncio.gather(
                    p1.send_message(msg),
                    p2.send_message(msg)
                )
                asyncio.create_task(self.start_game(p1, p2))
            except Exception as e:
                self._logger.exception(
                    "Error processing match between searches %s, and %s: %s",
                    s1, s2, e
                )

    async def start_game(self, host: Player, guest: Player):
        try:
            self._logger.debug(
                "Starting ladder game between %s and %s", host, guest
            )
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
            game.set_player_option(host.id, 'Army', 1)
            game.set_player_option(guest.id, 'Army', 2)
            game.set_player_option(host.id, 'Faction', host.faction.value)
            game.set_player_option(guest.id, 'Faction', guest.faction.value)
            game.set_player_option(host.id, 'Color', 1)
            game.set_player_option(guest.id, 'Color', 2)

            # Remembering that "Team 1" corresponds to "-": the non-team.
            game.set_player_option(host.id, 'Team', 1)
            game.set_player_option(guest.id, 'Team', 1)

            mapname = map_path[5:-4]
            # FIXME: Database filenames contain the maps/ prefix and .zip suffix.
            # Really in the future, just send a better description
            self._logger.debug("Starting ladder game: %s", game)
            # Options shared by guest and host
            options = GameLaunchOptions(
                mapname=mapname,
                team=1,
                expected_players=2,
            )
            await host.lobby_connection.launch_game(
                game,
                is_host=True,
                options=options._replace(
                    faction=host.faction,
                    map_position=1
                )
            )
            try:
                hosted = await game.await_hosted()
                if not hosted:
                    raise TimeoutError("Host left lobby")
            finally:
                # TODO: Once the client supports `game_launch_cancelled`, don't
                # send `launch_game` to the client if the host timed out. Until
                # then, failing to send `launch_game` will cause the client to
                # think it is searching for ladder, even though the server has
                # already removed it from the queue.

                # TODO: Graceful handling of NoneType errors due to disconnect
                await guest.lobby_connection.launch_game(
                    game,
                    is_host=False,
                    options=options._replace(
                        faction=guest.faction,
                        map_position=2
                    )
                )
            self._logger.debug("Ladder game launched successfully")
        except Exception:
            self._logger.exception("Failed to start ladder game!")
            msg = {"command": "game_launch_cancelled"}
            with contextlib.suppress(DisconnectedError):
                await asyncio.gather(
                    host.send_message(msg),
                    guest.send_message(msg)
                )

    async def choose_map(self, players: [Player]) -> MapDescription:
        maps = self.game_service.ladder_maps

        if not maps:
            self._logger.critical(
                "Trying to choose a map from an empty map pool!"
            )
            raise RuntimeError("Ladder maps not set!")

        recently_played_map_ids = {
            map_id for player in players
            for map_id in await self.get_ladder_history(
                player, limit=LADDER_ANTI_REPETITION_LIMIT
            )
        }
        randomized_maps = random.sample(maps, len(maps))

        return next(
            filter(
                lambda m: m[0] not in recently_played_map_ids,
                randomized_maps
            ),
            # If all maps were played recently, default to a random one
            randomized_maps[0]
        )

    async def get_ladder_history(self, player: Player, limit=3) -> List[int]:
        async with self._db.acquire() as conn:
            query = select([
                game_stats.c.mapId,
            ]).select_from(
                game_player_stats.join(game_stats).join(game_featuredMods)
            ).where(
                and_(
                    game_player_stats.c.playerId == player.id,
                    game_stats.c.startTime >=
                    func.now() - text("interval 1 day"),
                    game_featuredMods.c.gamemod == "ladder1v1"
                )
            ).order_by(game_stats.c.startTime.desc()).limit(limit)

            # Collect all the rows from the ResultProxy
            return [
                row[game_stats.c.mapId]
                async for row in await conn.execute(query)
            ]

    async def on_connection_lost(self, player):
        await self.cancel_search(player)
        if player in self._informed_players:
            self._informed_players.remove(player)

    async def shutdown(self):
        for queue in self.queues.values():
            queue.shutdown()
