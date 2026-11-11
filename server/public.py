"""
Public read-only http server for the game list and matchmaker queues.

For websites and apps that show games and queues without a lobby
connection. Two routes:

`GET /games`, two lists:
- `games`: open lobbies that are public and custom or coop.
- `live`: public games that have started, of any type, plus matchmaker games
  from the moment the match is made (while the players' games are starting).

`GET /matchmaker`: the running matchmaker queues, as `matchmaker_info` sends
them: how many are searching, their rating ranges, and the next queue pop.

All of it is what every signed-in client already receives, with a fixed set
of fields. Friends-only games are never listed. Viewers are anonymous, so
per-player rules (a host's foe list, rating restrictions) cannot be applied
here; they still apply when joining.
"""

import asyncio
import json
import logging
import socket
from typing import TYPE_CHECKING, Callable, ClassVar, Optional, cast

from aiohttp import web

from .config import config
from .decorators import with_logger
from .game_service import GameService
from .games import Game, GameState, GameType, VisibilityState

if TYPE_CHECKING:
    from server import ServerInstance
    from server.ladder_service import LadderService
    from server.matchmaker import MatchmakerQueue


# The fields of `Game.to_dict` that are published. Anything not named here,
# including fields added to `to_dict` later, stays private.
PUBLIC_GAME_FIELDS = (
    "uid",
    "title",
    "state",
    "game_type",
    "featured_mod",
    "sim_mods",
    "mapname",
    "host",
    "num_players",
    "max_players",
    "password_protected",
    "hosted_at",
    "rating_type",
    "rating_min",
    "rating_max",
    "enforce_rating_range",
    "teams",
)

# Live games also say when they started.
LIVE_GAME_FIELDS = PUBLIC_GAME_FIELDS + ("launched_at",)

PUBLIC_GAME_TYPES = (GameType.CUSTOM, GameType.COOP)


def is_public_lobby(game: Game) -> bool:
    return (
        game.state is GameState.LOBBY
        and game.visibility is VisibilityState.PUBLIC
        and game.game_type in PUBLIC_GAME_TYPES
        and game.host is not None
    )


def is_live_game(game: Game) -> bool:
    """
    A started game, or a matchmaker game whose players are joining.

    Matchmaker games are listed from the lobby state on, so a website can tell
    a player their match was found while their client is still starting it.
    """
    return (
        game.visibility is VisibilityState.PUBLIC
        and game.host is not None
        and (
            game.state is GameState.LIVE
            or (
                game.state is GameState.LOBBY
                and game.game_type is GameType.MATCHMAKER
            )
        )
    )


def public_game_dict(game: Game) -> dict:
    info = game.to_dict()
    return {field: info[field] for field in PUBLIC_GAME_FIELDS}


def live_game_dict(game: Game) -> dict:
    info = game.to_dict()
    return {field: info[field] for field in LIVE_GAME_FIELDS}


# The fields of `MatchmakerQueue.to_dict` that are published.
PUBLIC_QUEUE_FIELDS = (
    "queue_name",
    "queue_pop_time",
    "queue_pop_time_delta",
    "num_players",
    "boundary_80s",
    "boundary_75s",
    "team_size",
)


def public_queue_dict(queue: "MatchmakerQueue") -> dict:
    info = queue.to_dict()
    return {field: info[field] for field in PUBLIC_QUEUE_FIELDS}


@with_logger
class PublicServer:
    _logger: ClassVar[logging.Logger]

    def __init__(
        self,
        lobby_server: "ServerInstance",
    ):
        self.game_service = cast(GameService, lobby_server.services["game_service"])
        self.ladder_service = cast(
            "LadderService", lobby_server.services["ladder_service"]
        )
        self.host: Optional[str] = None
        self.port: Optional[int] = None
        self._bodies: dict[str, tuple[float, str]] = {}

        self.app = web.Application()
        self.runner = web.AppRunner(self.app)

        self.app.add_routes([
            web.get("/games", self.games),
            web.get("/matchmaker", self.matchmaker),
        ])

    async def run_from_config(self) -> None:
        """
        Initialize the public http server
        """
        host = socket.gethostbyname(socket.gethostname())
        port = config.PUBLIC_SERVER_PORT

        await self.shutdown()
        await self.start(host, port)

    async def start(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        self._logger.info(
            "Public server listening on http://%s:%s", host, port
        )

    async def shutdown(self) -> None:
        await self.runner.cleanup()
        self.host = None
        self.port = None

    def _cached(self, key: str, build: Callable[[], dict]) -> str:
        # Every request is served from one serialized copy, rebuilt at most
        # once per PUBLIC_SERVER_CACHE_SECONDS, so request volume does not
        # translate into work on the game list or the queues.
        now = asyncio.get_running_loop().time()
        cached = self._bodies.get(key)
        if cached is None or now - cached[0] >= config.PUBLIC_SERVER_CACHE_SECONDS:
            cached = (now, json.dumps(build()))
            self._bodies[key] = cached
        return cached[1]

    def _respond(self, body: str) -> web.Response:
        max_age = max(0, int(config.PUBLIC_SERVER_CACHE_SECONDS))
        return web.Response(
            text=body,
            content_type="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": f"public, max-age={max_age}",
            },
        )

    def _games(self) -> dict:
        games = list(self.game_service.all_games)
        return {
            "games": [
                public_game_dict(game)
                for game in games
                if is_public_lobby(game)
            ],
            "live": [
                live_game_dict(game)
                for game in games
                if is_live_game(game)
            ],
        }

    def _queues(self) -> dict:
        return {
            "queues": [
                public_queue_dict(queue)
                for queue in self.ladder_service.queues.values()
                if queue.is_running
            ]
        }

    async def games(self, request: web.Request) -> web.Response:
        return self._respond(self._cached("games", self._games))

    async def matchmaker(self, request: web.Request) -> web.Response:
        return self._respond(self._cached("matchmaker", self._queues))
