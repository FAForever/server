"""
Manages interactions between players and matchmakers
"""

import asyncio
import json
import random
import re
from collections import defaultdict
from typing import Optional

import aiocron
from sqlalchemy import and_, func, select, text, true

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
from .matchmaker import MapPool, MatchmakerQueue, OnMatchedCallback, Search
from .players import Player, PlayerState
from .types import GameLaunchOptions, Map, NeroxisGeneratedMap


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
        self._informed_players: set[Player] = set()
        self.game_service = game_service
        self.queues = {}

        self._searches: dict[Player, dict[str, Search]] = defaultdict(dict)

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
                    params=info.get("params")
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

    async def fetch_map_pools(self, conn) -> dict[int, tuple[str, list[Map]]]:
        result = await conn.execute(
            select([
                map_pool.c.id,
                map_pool.c.name,
                map_pool_map_version.c.weight,
                map_pool_map_version.c.map_params,
                map_version.c.id.label("map_id"),
                map_version.c.filename,
                t_map.c.display_name
            ]).select_from(
                map_pool.outerjoin(map_pool_map_version)
                .outerjoin(map_version)
                .outerjoin(t_map)
            )
        )
        map_pool_maps = {}
        for row in result:
            id_ = row.id
            name = row.name
            if id_ not in map_pool_maps:
                map_pool_maps[id_] = (name, list())
            _, map_list = map_pool_maps[id_]
            if row.map_id is not None:
                map_list.append(
                    Map(row.map_id, row.display_name, row.filename, row.weight)
                )
            elif row.map_params is not None:
                try:
                    params = json.loads(row.map_params)
                    map_type = params["type"]
                    if map_type == "neroxis":
                        map_list.append(
                            NeroxisGeneratedMap.of(params, row.weight)
                        )
                    else:
                        self._logger.warning(
                            "Unsupported map type %s in pool %s",
                            map_type,
                            row.id
                        )

                except Exception:
                    self._logger.warning(
                        "Failed to load map in map pool %d. "
                        "Parameters are '%s'",
                        row.id,
                        row.map_params,
                        exc_info=True
                    )

        return map_pool_maps

    async def fetch_matchmaker_queues(self, conn):
        result = await conn.execute(
            select([
                matchmaker_queue.c.id,
                matchmaker_queue.c.technical_name,
                matchmaker_queue.c.team_size,
                matchmaker_queue.c.params,
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
        # So we don't log the same error multiple times when a queue has several
        # map pools
        errored = set()
        matchmaker_queues = defaultdict(lambda: defaultdict(list))
        for row in result:
            name = row.technical_name
            if name in errored:
                continue
            info = matchmaker_queues[name]
            try:
                info["id"] = row.id
                info["mod"] = row.gamemod
                info["rating_type"] = row.rating_type
                info["team_size"] = row.team_size
                info["params"] = json.loads(row.params) if row.params else None
                info["map_pools"].append((
                    row.map_pool_id,
                    row.min_rating,
                    row.max_rating
                ))
            except Exception:
                self._logger.warning(
                    "Unable to load queue '%s'!",
                    name,
                    exc_info=True
                )
                del matchmaker_queues[name]
                errored.add(name)
        return matchmaker_queues

    def start_search(
        self,
        players: list[Player],
        queue_name: str,
        on_matched: OnMatchedCallback = lambda _1, _2: None
    ):
        # Cancel any existing searches that players have for this queue
        for player in players:
            if queue_name in self._searches[player]:
                self._cancel_search(player, queue_name)

        queue = self.queues[queue_name]
        search = Search(
            players,
            rating_type=queue.rating_type,
            on_matched=on_matched
        )

        for player in players:
            player.state = PlayerState.SEARCHING_LADDER

            self.write_rating_progress(player, queue.rating_type)

            player.write_message({
                "command": "search_info",
                "queue_name": queue_name,
                "state": "start"
            })

            self._searches[player][queue_name] = search

        self._logger.info("%s started searching for %s", search, queue_name)

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
        cancelled_search = self._clear_search(initiator, queue_name)
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

    def _clear_search(
        self,
        initiator: Player,
        queue_name: str
    ) -> Optional[Search]:
        """
        Remove a search from the searches dictionary.

        Does NOT cancel the search.
        """
        search = self._searches[initiator].get(queue_name)

        if search is not None:
            for player in search.players:
                del self._searches[player][queue_name]

        return search

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
                        "The matchmaking system is calibrating your skill level; "
                        "your first few games may be slightly more imbalanced "
                        "as the system attempts to learn your capability as a player."
                        "<br><br>"
                        f"<b>The learning phase is {progress:.0f}% completed</b>"
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
            msg = {"command": "match_found", "queue_name": queue.name}

            for player in s1.players + s2.players:
                player.state = PlayerState.STARTING_AUTOMATCH
                player.write_message(msg)

                # Cancel any other searches
                queue_names = list(
                    name for name in self._searches[player].keys()
                    if name != queue.name
                )
                for queue_name in queue_names:
                    self._cancel_search(player, queue_name)

                self._clear_search(player, queue.name)

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
        team1: list[Player],
        team2: list[Player],
        queue: MatchmakerQueue
    ) -> None:
        assert len(team1) == len(team2)

        self._logger.debug(
            "Starting %s game between %s and %s",
            queue.name,
            [p.login for p in team1],
            [p.login for p in team2]
        )
        game = None
        try:
            host = team1[0]
            all_players = team1 + team2
            all_guests = all_players[1:]

            played_map_ids = await self.get_game_history(
                all_players,
                queue.id,
                limit=config.LADDER_ANTI_REPETITION_LIMIT
            )
            rating = min(
                player.ratings[queue.rating_type].displayed()
                for player in all_players
            )
            pool = queue.get_map_pool_for_rating(rating)
            if not pool:
                raise RuntimeError(f"No map pool available for rating {rating}!")
            _, _, map_path, _ = pool.choose_map(played_map_ids)

            game = self.game_service.create_game(
                game_class=LadderGame,
                game_mode=queue.featured_mod,
                host=host,
                name="Matchmaker Game",
                matchmaker_queue_id=queue.id,
                rating_type=queue.rating_type,
                max_players=len(all_players)
            )
            game.map_file_path = map_path
            game.set_name_unchecked(game_name(team1, team2))

            def get_player_mean(player):
                return player.ratings[queue.rating_type][0]

            team1 = sorted(team1, key=get_player_mean)
            team2 = sorted(team2, key=get_player_mean)

            # Shuffle the teams such that direct opponents remain the same
            zipped_teams = list(zip(team1, team2))
            random.shuffle(zipped_teams)

            for i, player in enumerate(
                player for pair in zipped_teams for player in pair
            ):
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

            game_options = queue.get_game_options()
            if game_options:
                game.gameOptions.update(game_options)

            mapname = re.match("maps/(.+).zip", map_path).group(1)
            # FIXME: Database filenames contain the maps/ prefix and .zip suffix.
            # Really in the future, just send a better description

            self._logger.debug("Starting ladder game: %s", game)
            # Options shared by all players
            options = GameLaunchOptions(
                mapname=mapname,
                expected_players=len(all_players),
                game_options=game_options
            )

            def game_options(player: Player) -> GameLaunchOptions:
                return options._replace(
                    team=game.get_player_option(player.id, "Team"),
                    faction=player.faction,
                    map_position=game.get_player_option(player.id, "StartSpot")
                )

            # Tell the host to launch
            await host.lobby_connection.launch_game(
                game, is_host=True, options=game_options(host)
            )
            await game.wait_hosted(60)

            # Tell the guests to launch
            await asyncio.gather(*[
                guest.lobby_connection.launch_game(
                    game, is_host=False, options=game_options(guest)
                )
                for guest in all_guests
                if guest.lobby_connection is not None
            ])
            await game.wait_launched(60 + 10 * len(all_guests))

            self._logger.debug("Ladder game launched successfully %s", game)
        except Exception:
            if game:
                await game.on_game_end()

            msg = {"command": "match_cancelled"}
            for player in all_players:
                if player.state == PlayerState.STARTING_AUTOMATCH:
                    player.state = PlayerState.IDLE
                player.write_message(msg)

    async def get_game_history(
        self,
        players: list[Player],
        queue_id: int,
        limit: int = 3
    ) -> list[int]:
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
                    row.mapId for row in await conn.execute(query)
                ])
        return result

    def on_connection_lost(self, conn: "LobbyConnection") -> None:
        if not conn.player:
            return

        player = conn.player
        self.cancel_search(player)
        del self._searches[player]
        if player in self._informed_players:
            self._informed_players.remove(player)

    async def shutdown(self):
        for queue in self.queues.values():
            queue.shutdown()


def game_name(*teams: list[Player]) -> str:
    """
    Generate a game name based on the players.
    """

    return " Vs ".join(_team_name(team) for team in teams)


def _team_name(team: list[Player]) -> str:
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
