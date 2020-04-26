import asyncio
import contextlib
from collections import defaultdict
from typing import Dict, List, Set

import aiocron
from server.db import FAFDatabase
from server.rating import RatingType
from sqlalchemy import and_, func, select, text

from .async_functions import gather_without_exceptions
from .config import config
from .core import Service
from .db.models import game_featuredMods, game_player_stats, game_stats
from .db.models import map as t_map
from .db.models import (
    map_pool, map_pool_map_version, map_version, matchmaker_queue,
    matchmaker_queue_map_pool
)
from .decorators import with_logger
from .game_service import GameService
from .matchmaker import MapPool, MatchmakerQueue, Search
from .players import Player, PlayerState
from .protocol import DisconnectedError
from .types import GameLaunchOptions, Map


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

        # Fallback legacy map pool and matchmaker queue
        self.ladder_1v1_map_pool = MapPool(0, "ladder1v1")
        self.queues = {
            'ladder1v1': MatchmakerQueue(
                game_service,
                'ladder1v1',
                'ladder1v1',
                map_pools=[(self.ladder_1v1_map_pool, None, None)]
            )
        }

        self.searches: Dict[str, Dict[Player, Search]] = defaultdict(dict)

    async def initialize(self) -> None:
        await self.update_data()
        self._update_cron = aiocron.crontab('*/10 * * * *', func=self.update_data)
        await asyncio.gather(*[
            queue.initialize() for queue in self.queues.values()
        ])
        asyncio.create_task(self.handle_queue_matches())

    async def update_data(self) -> None:
        async with self._db.acquire() as conn:
            # Legacy ladder1v1 map pool
            result = await conn.execute(
                "SELECT ladder_map.idmap, "
                "table_map.name, "
                "table_map.filename "
                "FROM ladder_map "
                "INNER JOIN table_map ON table_map.id = ladder_map.idmap"
            )
            maps = [
                Map(row[0], row[1], row[2]) async for row in result
            ]
            self.ladder_1v1_map_pool.set_maps(maps)

            # New map pools
            result = await conn.execute(
                select([
                    map_pool.c.id,
                    map_pool.c.name,
                    map_version.c.map_id,
                    map_version.c.filename,
                    t_map.c.display_name
                ]).select_from(
                    map_pool.join(map_pool_map_version)
                    .join(map_version)
                    .join(t_map)
                )
            )
            map_pool_maps = {}
            async for row in result:
                id_ = row[map_pool.c.id]
                name = row[map_pool.c.name]
                if id_ not in map_pool_maps:
                    map_pool_maps[id_] = (name, list())
                _, map_list = map_pool_maps[id_]
                map_list.append(
                    Map(
                        row[map_version.c.map_id],
                        row[t_map.c.display_name],
                        row[map_version.c.filename]
                    )
                )

            # Update the matchmaker queues
            result = await conn.execute(
                select([matchmaker_queue, matchmaker_queue_map_pool])
                .select_from(matchmaker_queue.join(matchmaker_queue_map_pool))
            )

            queue_names = set()
            async for row in result:
                name = row[matchmaker_queue.c.technical_name]
                if name not in self.queues:
                    self.queues[name] = MatchmakerQueue(
                        name=name,
                        name_key=row[matchmaker_queue.c.name_key],
                        game_service=self.game_service
                    )
                queue = self.queues[name]
                if name not in queue_names:
                    queue.map_pools.clear()
                map_pool_id = row[matchmaker_queue_map_pool.c.map_pool_id]
                map_pool_name, map_list = map_pool_maps[map_pool_id]
                queue.add_map_pool(
                    MapPool(map_pool_id, map_pool_name, map_list),
                    row[matchmaker_queue_map_pool.c.min_rating],
                    row[matchmaker_queue_map_pool.c.max_rating]
                )
                queue_names.add(name)
            # Remove queues that don't exist anymore
            for queue_name in list(self.queues.keys()):
                if queue_name not in queue_names:
                    del self.queues[queue_name]

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

            played_map_ids = await self.get_game_history(
                [host, guest],
                "ladder1v1",
                limit=config.LADDER_ANTI_REPETITION_LIMIT
            )
            rating = min(
                player.ratings[RatingType.LADDER_1V1][0]
                if (
                    player.game_count[RatingType.LADDER_1V1] >
                    config.NEWBIE_MIN_GAMES
                ) else 0
                for player in (host, guest)
            )
            map_pool = self.queues["ladder1v1"].get_map_pool_for_rating(rating)
            if not map_pool:
                raise RuntimeError(f"No map pool available for rating {rating}!")
            (map_id, map_name, map_path) = map_pool.choose_map(played_map_ids)

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

    async def get_game_history(
        self,
        players: List[Player],
        mod: str,
        limit=3
    ) -> List[int]:
        async with self._db.acquire() as conn:
            result = []
            for player in players:
                query = select([
                    game_stats.c.mapId,
                ]).select_from(
                    game_player_stats.join(game_stats).join(game_featuredMods)
                ).where(
                    and_(
                        game_player_stats.c.playerId == player.id,
                        game_stats.c.startTime >=
                        func.now() - text("interval 1 day"),
                        game_featuredMods.c.gamemod == mod
                    )
                ).order_by(game_stats.c.startTime.desc()).limit(limit)

            result.extend([
                row[game_stats.c.mapId]
                async for row in await conn.execute(query)
            ])
        return result

    async def on_connection_lost(self, player):
        await self.cancel_search(player)
        if player in self._informed_players:
            self._informed_players.remove(player)

    async def shutdown(self):
        for queue in self.queues.values():
            queue.shutdown()
