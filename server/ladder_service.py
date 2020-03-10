import asyncio
import contextlib
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import aiocron
from sqlalchemy import and_, func, select, text

from .abc.base_game import InitMode
from .async_functions import gather_without_exceptions
from .config import config
from .core import Service
from .db import FAFDatabase
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
from .rating import RatingType
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
                name='ladder1v1',
                map_pools=[(self.ladder_1v1_map_pool, None, None)]
            ),
            'ladder2v2': MatchmakerQueue(
                game_service=game_service,
                name='ladder2v2',
                min_team_size=2,
                max_team_size=2
            )
        }

        self.searches: Dict[str, Dict[Player, Search]] = defaultdict(dict)

    async def initialize(self) -> None:
        await self.update_data()
        self._update_cron = aiocron.crontab('*/10 * * * *', func=self.update_data)
        await asyncio.gather(*[
            queue.initialize() for queue in self.queues.values()
        ])
        self.start_queue_handlers()

    async def update_data(self) -> None:
        async with self._db.acquire() as conn:
            # Legacy ladder1v1 map pool
            # TODO: Remove this https://github.com/FAForever/server/issues/581
            result = await conn.execute(
                "SELECT ladder_map.idmap, "
                "table_map.name, "
                "table_map.filename "
                "FROM ladder_map "
                "INNER JOIN table_map ON table_map.id = ladder_map.idmap"
            )
            maps = [Map(*row.as_tuple()) async for row in result]

            self.ladder_1v1_map_pool.set_maps(maps)

            map_pool_maps = await self.fetch_map_pools(conn)
            matchmaker_queues = await self.fetch_matchmaker_queues(conn)

        for name, map_pools in matchmaker_queues.items():
            if name not in self.queues:
                self.queues[name] = MatchmakerQueue(
                    name=name,
                    game_service=self.game_service
                )
            queue = self.queues[name]
            queue.map_pools.clear()
            for map_pool_id, min_rating, max_rating in map_pools:
                map_pool_name, map_list = map_pool_maps[map_pool_id]
                if not map_list:
                    self._logger.warning(
                        "Map pool '%s' is empty! Some %s games will "
                        "likely fail to start!",
                        map_pool_name,
                        name
                    )
                queue.add_map_pool(
                    MapPool(map_pool_id, map_pool_name, map_list),
                    min_rating,
                    max_rating
                )
        # Remove queues that don't exist anymore
        for queue_name in list(self.queues.keys()):
            if queue_name in ("ladder1v1", "ladder2v2"):
                # TODO: Remove me. Legacy queue fallback
                continue
            if queue_name not in matchmaker_queues:
                self.queues[queue_name].shutdown()
                del self.queues[queue_name]

    async def fetch_map_pools(self, conn) -> Dict[int, Tuple[str, List[Map]]]:
        result = await conn.execute(
            select([
                map_pool.c.id,
                map_pool.c.name,
                map_version.c.map_id,
                map_version.c.filename,
                t_map.c.display_name
            ]).select_from(
                map_pool.outerjoin(map_pool_map_version)
                .outerjoin(map_version)
                .outerjoin(t_map)
            )
        )
        map_pool_maps = {}
        async for row in result:
            id_ = row.id
            name = row.name
            if id_ not in map_pool_maps:
                map_pool_maps[id_] = (name, list())
            _, map_list = map_pool_maps[id_]
            if row.map_id is not None:
                map_list.append(
                    Map(row.map_id, row.display_name, row.filename)
                )

        return map_pool_maps

    async def fetch_matchmaker_queues(self, conn) -> Dict[str, Tuple[int, int, int]]:
        result = await conn.execute(
            select([
                matchmaker_queue.c.technical_name,
                matchmaker_queue_map_pool.c.map_pool_id,
                matchmaker_queue_map_pool.c.min_rating,
                matchmaker_queue_map_pool.c.max_rating
            ])
            .select_from(matchmaker_queue.join(matchmaker_queue_map_pool))
        )

        matchmaker_queues = defaultdict(list)
        async for row in result:
            name = row.technical_name
            matchmaker_queues[name].append((
                row.map_pool_id,
                row.min_rating,
                row.max_rating
            ))
        return matchmaker_queues

    async def start_search(
        self,
        initiator: Player,
        search: Search,
        queue_name: str
    ):
        # TODO: Consider what happens if players disconnect while starting
        # search. Will need a message to inform other players in the search
        # that it has been cancelled.
        self._cancel_existing_searches(initiator, queue_name)

        tasks = []
        for player in search.players:
            player.state = PlayerState.SEARCHING_LADDER

            # For now, inform_player is only designed for ladder1v1
            if queue_name == "ladder1v1":
                tasks.append(self.inform_player(player))

            tasks.append(player.send_message({
                "command": "search_info",
                "queue": queue_name,
                "state": "start"
            }))

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

    async def cancel_search(
        self,
        initiator: Player,
        queue_name: Optional[str] = None
    ):
        searches = self._cancel_existing_searches(initiator, queue_name)

        tasks = []
        for queue_name, search in searches:
            for player in search.players:
                # FIXME: This is wrong for multiqueueing
                if player.state == PlayerState.SEARCHING_LADDER:
                    player.state = PlayerState.IDLE

                if player.lobby_connection is not None:
                    tasks.append(player.send_message({
                        "command": "search_info",
                        "queue": queue_name,
                        "state": "stop"
                    }))
            self._logger.info(
                "%s stopped searching for %s: %s", initiator, queue_name, search
            )

        await gather_without_exceptions(tasks, DisconnectedError)

    def _cancel_existing_searches(
        self,
        initiator: Player,
        queue_name: Optional[str] = None
    ) -> List[Tuple[str, Search]]:
        """
        Cancel search for a specific queue, or all searches if `queue_name` is
        None.
        """
        if queue_name:
            queue_names = [queue_name]
        else:
            queue_names = list(self.queues)

        searches = []
        for queue_name in queue_names:
            search = self.searches[queue_name].get(initiator)
            if search:
                search.cancel()
                searches.append((queue_name, search))
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
                        f"learning phase is {progress:.0f}% complete<b>"
                    )
                })

    def start_queue_handlers(self):
        for queue in self.queues:
            asyncio.ensure_future(self.handle_queue_matches(queue))

    async def handle_queue_matches(self, queue_name: str):
        async for s1, s2 in self.queues[queue_name].iter_matches():
            try:
                msg = {"command": "match_found", "queue": queue_name}
                # TODO: Handle disconnection with a client supported message
                await asyncio.gather(*[
                    player.send_message(msg)
                    for player in s1.players + s2.players
                ])
                asyncio.create_task(
                    self.start_game(s1.players, s2.players, queue_name)
                )
            except Exception as e:
                self._logger.exception(
                    "Error processing match between searches %s, and %s: %s",
                    s1, s2, e
                )

    async def start_game(self, team1: List[Player], team2: List[Player], queue: str):
        # TODO: Get game_mode from queue
        self._logger.debug(
            "Starting %s game between %s and %s", queue, team1, team2
        )
        try:
            host = team1[0]
            all_players = team1 + team2
            all_guests = all_players[1:]

            host.state = PlayerState.HOSTING
            for guest in all_guests:
                guest.state = PlayerState.JOINING

            played_map_ids = await self.get_game_history(
                all_players,
                "ladder1v1",
                limit=config.LADDER_ANTI_REPETITION_LIMIT
            )
            rating = min(
                newbie_adjusted_ladder_mean(player)
                for player in all_players
            )
            pool = self.queues["ladder1v1"].get_map_pool_for_rating(rating)
            if not pool:
                raise RuntimeError(f"No map pool available for rating {rating}!")
            map_id, map_name, map_path = pool.choose_map(played_map_ids)

            # TODO: Different game mode for team matchmaker?
            game = self.game_service.create_game(
                game_mode=queue,
                host=host,
                name=self.game_name(team1, team2)
            )
            game.init_mode = InitMode.AUTO_LOBBY
            game.map_file_path = map_path

            for i, player in enumerate(all_players):
                i += 1  # Game options are 1-indexed
                player.game = game

                # Configure game options
                game.set_player_option(player.id, 'Faction', player.faction.value)
                game.set_player_option(player.id, 'Color', i)
                game.set_player_option(player.id, 'Army', i+1)

            for i, player in enumerate(team1):
                game.set_player_option(player.id, 'Team', 2)
                # Team 1 gets odd numbered start spots
                game.set_player_option(player.id, 'StartSpot', 2 * i + 1)

            for i, player in enumerate(team2):
                game.set_player_option(player.id, 'Team', 3)
                # Team 2 gets even numbered start spots
                game.set_player_option(player.id, 'StartSpot', 2 * (i + 1))

            mapname = re.match('maps/(.+).zip', map_path).group(1)
            # FIXME: Database filenames contain the maps/ prefix and .zip suffix.
            # Really in the future, just send a better description
            self._logger.debug("Starting ladder game: %s", game)
            # Options shared by all players
            options = GameLaunchOptions(
                mapname=mapname,
                expected_players=len(all_players),
            )

            def game_options(player: Player) -> GameLaunchOptions:
                return options._replace(
                    team=game.get_player_option(player.id, "Team"),
                    faction=player.faction,
                    map_position=game.get_player_option(player.id, "StartSpot")
                )

            await host.lobby_connection.launch_game(
                game, is_host=True, options=game_options(host)
            )
            try:
                hosted = await game.await_hosted()
                if not hosted:
                    raise TimeoutError("Host left lobby")
            finally:
                # TODO: Once the client supports `match_cancelled`, don't
                # send `launch_game` to the client if the host timed out. Until
                # then, failing to send `launch_game` will cause the client to
                # think it is searching for ladder, even though the server has
                # already removed it from the queue.

                # TODO: Graceful handling of NoneType errors due to disconnect
                await asyncio.gather(*[
                    guest.lobby_connection.launch_game(
                        game, is_host=False, options=game_options(guest)
                    )
                    for guest in all_guests
                ])
                # TODO: Wait for players to join here
            self._logger.debug("Ladder game launched successfully")
        except Exception:
            self._logger.exception("Failed to start ladder game!")
            msg = {"command": "match_cancelled"}
            with contextlib.suppress(DisconnectedError):
                await asyncio.gather(*[
                    player.lobby_connection.send(msg) for player in all_players
                ])

    def game_name(self, team1: List[Player], team2: List[Player]) -> str:
        """
        Generate a game name based on the players.
        """
        team1_name = self._team_name(team1)
        team2_name = self._team_name(team2)

        return f"{team1_name} Vs {team2_name}"

    def _team_name(self, team: List[Player]):
        """
        Generate a team name based on the players. If all players are in the
        same clan, use their clan name, otherwise use the name of the first
        player.
        """
        assert team

        player_1_name = team[0].login

        if len(team) == 1:
            return player_1_name

        clans = {p.clan for p in team}

        if len(clans) == 1:
            name = clans.pop() or player_1_name
        else:
            name = player_1_name

        return f"Team {name}"

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
                        game_stats.c.startTime >= func.DATE_SUB(
                            func.now(),
                            text("interval 1 day")
                        ),
                        game_featuredMods.c.gamemod == mod
                    )
                ).order_by(game_stats.c.startTime.desc()).limit(limit)

            result.extend([
                row.mapId async for row in await conn.execute(query)
            ])
        return result

    async def on_connection_lost(self, player):
        await self.cancel_search(player)
        if player in self._informed_players:
            self._informed_players.remove(player)

    async def shutdown(self):
        for queue in self.queues.values():
            queue.shutdown()


def newbie_adjusted_ladder_mean(player: Player):
    """Get ladder rating mean with new player's always returning a mean of 0"""
    if player.game_count[RatingType.LADDER_1V1] > config.NEWBIE_MIN_GAMES:
        return player.ratings[RatingType.LADDER_1V1][0]
    else:
        return 0
