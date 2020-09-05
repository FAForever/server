import asyncio
import contextlib
import itertools
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import aiocron
from sqlalchemy import and_, func, select, text, true

from .abc.base_game import InitMode
from .config import config
from .core import Service
from .db import FAFDatabase
from .db.models import (
    game_featuredMods,
    game_player_stats,
    game_stats,
    leaderboard
)
from .db.models import map as t_map
from .db.models import (
    map_pool,
    map_pool_map_version,
    map_version,
    matchmaker_queue,
    matchmaker_queue_game,
    matchmaker_queue_map_pool
)
from .decorators import with_logger
from .game_service import GameService
from .games import LadderGame
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
        self.queues = {}

        self._searches: Dict[Player, Dict[str, Search]] = defaultdict(dict)

    async def initialize(self) -> None:
        await self.update_data()
        self._update_cron = aiocron.crontab("*/10 * * * *", func=self.update_data)

    async def update_data(self) -> None:
        async with self._db.acquire() as conn:
            map_pool_maps = await self.fetch_map_pools(conn)
            db_queues = await self.fetch_matchmaker_queues(conn)

        for name, info in db_queues.items():
            if name not in self.queues:
                queue = MatchmakerQueue(
                    self.game_service,
                    self.on_match_found,
                    name=name,
                    queue_id=info["id"],
                    featured_mod=info["mod"],
                    rating_type=info["rating_type"],
                    team_size=info["team_size"],
                )
                self.queues[name] = queue
                queue.initialize()
            else:
                queue = self.queues[name]
                queue.featured_mod = info["mod"]
                queue.rating_type = info["rating_type"]
                queue.team_size = info["team_size"]
            queue.map_pools.clear()
            for map_pool_id, min_rating, max_rating in info["map_pools"]:
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
            if queue_name not in db_queues:
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

    async def fetch_matchmaker_queues(self, conn):
        result = await conn.execute(
            select([
                matchmaker_queue.c.id,
                matchmaker_queue.c.technical_name,
                matchmaker_queue.c.team_size,
                matchmaker_queue_map_pool.c.map_pool_id,
                matchmaker_queue_map_pool.c.min_rating,
                matchmaker_queue_map_pool.c.max_rating,
                game_featuredMods.c.gamemod,
                leaderboard.c.technical_name.label("rating_type")
            ])
            .select_from(
                matchmaker_queue
                .join(matchmaker_queue_map_pool)
                .join(game_featuredMods)
                .join(leaderboard)
            ).where(matchmaker_queue.c.enabled == true())
        )
        matchmaker_queues = defaultdict(lambda: defaultdict(list))
        async for row in result:
            name = row.technical_name
            info = matchmaker_queues[name]
            info["id"] = row.id
            info["mod"] = row.gamemod
            info["rating_type"] = row.rating_type
            info["team_size"] = row.team_size
            info["map_pools"].append((
                row.map_pool_id,
                row.min_rating,
                row.max_rating
            ))
        return matchmaker_queues

    def start_search(self, players: List[Player], queue_name: str):
        # Cancel any existing searches that players have for this queue
        for player in players:
            if queue_name in self._searches[player]:
                self._cancel_search(player, queue_name)

        queue = self.queues[queue_name]
        search = Search(players, rating_type=queue.rating_type)

        for player in players:
            player.state = PlayerState.SEARCHING_LADDER

            self.write_rating_progress(player, queue.rating_type)

            player.write_message({
                "command": "search_info",
                "queue_name": queue_name,
                "state": "start"
            })

            self._searches[player][queue_name] = search

        self._logger.info(
            "%s are searching for '%s': %s", players, queue_name, search
        )

        asyncio.create_task(queue.search(search))

    def cancel_search(
        self,
        initiator: Player,
        queue_name: Optional[str] = None
    ) -> None:
        if queue_name is None:
            queue_names = list(self._searches[initiator].keys())
        else:
            queue_names = [queue_name]

        for queue_name in queue_names:
            self._cancel_search(initiator, queue_name)

    def _cancel_search(self, initiator: Player, queue_name: str) -> None:
        """
        Cancel search for a specific player/queue.
        """
        cancelled_search = self._searches[initiator].get(queue_name)
        if cancelled_search is None:
            self._logger.debug(
                "Ignoring request to cancel a search that does not exist: "
                "%s, %s",
                initiator,
                queue_name
            )
            return
        cancelled_search.cancel()

        for player in cancelled_search.players:
            del self._searches[player][queue_name]
            player.write_message({
                "command": "search_info",
                "queue_name": queue_name,
                "state": "stop"
            })
            if (
                not self._searches[player]
                and player.state == PlayerState.SEARCHING_LADDER
            ):
                player.state = PlayerState.IDLE
        self._logger.info(
            "%s stopped searching for %s", cancelled_search, queue_name
        )

    def write_rating_progress(self, player: Player, rating_type: str) -> None:
        if player not in self._informed_players:
            self._informed_players.add(player)
            _, deviation = player.ratings[rating_type]

            if deviation > 490:
                player.write_message({
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
                player.write_message({
                    "command": "notice",
                    "style": "info",
                    "text": (
                        "The system is still learning you.<b><br><br>The "
                        f"learning phase is {progress:.0f}% complete<b>"
                    )
                })

    def on_match_found(
        self,
        s1: Search,
        s2: Search,
        queue: MatchmakerQueue
    ) -> None:
        """
        Callback for when a match is generated by a matchmaker queue.

        NOTE: This function is called while the matchmaker search lock is held,
        so it should only perform fast operations.
        """
        try:
            msg = {"command": "match_found", "queue": queue.name}

            for player in s1.players + s2.players:
                player.write_message(msg)

                self.cancel_search(player)

            asyncio.create_task(
                self.start_game(s1.players, s2.players, queue)
            )
        except Exception:
            self._logger.exception(
                "Error processing match between searches %s, and %s",
                s1, s2
            )

    async def start_game(
        self,
        team1: List[Player],
        team2: List[Player],
        queue: MatchmakerQueue
    ) -> None:
        self._logger.debug(
            "Starting %s game between %s and %s", queue.name, team1, team2
        )
        game = None
        try:
            host = team1[0]
            all_players = team1 + team2
            all_guests = all_players[1:]

            host.state = PlayerState.HOSTING
            for guest in all_guests:
                guest.state = PlayerState.JOINING

            played_map_ids = await self.get_game_history(
                all_players,
                queue.id,
                limit=config.LADDER_ANTI_REPETITION_LIMIT
            )
            rating = min(
                newbie_adjusted_ladder_mean(player)
                for player in all_players
            )
            pool = queue.get_map_pool_for_rating(rating)
            if not pool:
                raise RuntimeError(f"No map pool available for rating {rating}!")
            map_id, map_name, map_path = pool.choose_map(played_map_ids)

            game = self.game_service.create_game(
                game_class=LadderGame,
                game_mode=queue.featured_mod,
                host=host,
                name=game_name(team1, team2),
                matchmaker_queue_id=queue.id,
                rating_type=queue.rating_type,
                max_players=len(all_players)
            )
            game.init_mode = InitMode.AUTO_LOBBY
            game.map_file_path = map_path

            for i, player in enumerate(alternate(team1, team2)):
                if player is None:
                    continue
                # FA uses lua and lua arrays are 1-indexed
                slot = i + 1
                # 2 if even, 3 if odd
                team = (i % 2) + 2
                player.game = game

                game.set_player_option(player.id, "Faction", player.faction.value)
                game.set_player_option(player.id, "Team", team)
                game.set_player_option(player.id, "StartSpot", slot)
                game.set_player_option(player.id, "Army", slot)
                game.set_player_option(player.id, "Color", slot)

            mapname = re.match("maps/(.+).zip", map_path).group(1)
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
                await game.wait_hosted(30)
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
            await game.wait_launched(30)
            self._logger.debug("Ladder game launched successfully")
        except Exception:
            if game:
                await game.on_game_end()
            self._logger.exception("Failed to start ladder game!")
            msg = {"command": "match_cancelled"}
            with contextlib.suppress(DisconnectedError):
                await asyncio.gather(*[
                    player.send_message(msg) for player in all_players
                ])

    async def get_game_history(
        self,
        players: List[Player],
        queue_id: int,
        limit=3
    ) -> List[int]:
        async with self._db.acquire() as conn:
            result = []
            for player in players:
                query = select([
                    game_stats.c.mapId,
                ]).select_from(
                    game_player_stats
                    .join(game_stats)
                    .join(matchmaker_queue_game)
                ).where(
                    and_(
                        game_player_stats.c.playerId == player.id,
                        game_stats.c.startTime >= func.DATE_SUB(
                            func.now(),
                            text("interval 1 day")
                        ),
                        matchmaker_queue_game.c.matchmaker_queue_id == queue_id
                    )
                ).order_by(game_stats.c.startTime.desc()).limit(limit)

                result.extend([
                    row.mapId async for row in await conn.execute(query)
                ])
        return result

    async def on_connection_lost(self, player):
        self.cancel_search(player)
        del self._searches[player]
        if player in self._informed_players:
            self._informed_players.remove(player)

    async def shutdown(self):
        for queue in self.queues.values():
            queue.shutdown()


def game_name(*teams: List[Player]) -> str:
    """
    Generate a game name based on the players.
    """

    return " Vs ".join(_team_name(team) for team in teams)


def _team_name(team: List[Player]) -> str:
    """
    Generate a team name based on the players. If all players are in the
    same clan, use their clan tag, otherwise use the name of the first
    player.
    """
    assert team

    player_1_name = team[0].login

    if len(team) == 1:
        return player_1_name

    clans = {player.clan for player in team}

    if len(clans) == 1:
        name = clans.pop() or player_1_name
    else:
        name = player_1_name

    return f"Team {name}"


def newbie_adjusted_ladder_mean(player: Player):
    """Get ladder rating mean with new player's always returning a mean of 0"""
    if player.game_count[RatingType.LADDER_1V1] > config.NEWBIE_MIN_GAMES:
        return player.ratings[RatingType.LADDER_1V1][0]
    else:
        return 0


def alternate(iter1, iter2):
    """
    Merge elements from two iterables, inserting None if one iterable is shorter.

    # Example
    list(alternate([1, 2, 3], ["a", "b"])) == [1, "a", 2, "b", 3, None]
    """
    for i, j in itertools.zip_longest(iter1, iter2):
        yield i
        yield j
