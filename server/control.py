"""
Tiny http server for introspecting state
"""

import socket

from aiohttp import web

from .config import config
from .decorators import with_logger


@with_logger
class ControlServer:
    def __init__(
        self,
        lobby_server: "ServerInstance",
    ):
        self.lobby_server = lobby_server
        self.game_service = lobby_server.services["game_service"]
        self.player_service = lobby_server.services["player_service"]
        self.host = None
        self.port = None

        self.app = web.Application()
        self.runner = web.AppRunner(self.app)

        self.app.add_routes([
            web.get("/games", self.games),
            web.get("/players", self.players),
        ])

    async def run_from_config(self) -> None:
        """
        Initialize the http control server
        """
        host = socket.gethostbyname(socket.gethostname())
        port = config.CONTROL_SERVER_PORT

        await self.shutdown()
        await self.start(host, port)

    async def start(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        self._logger.info(
            "Control server listening on http://%s:%s", host, port
        )

    async def shutdown(self) -> None:
        await self.runner.cleanup()
        self.host = None
        self.port = None

    async def games(self, request) -> web.Response:
        return web.json_response([
            game.to_dict()
            for game in self.game_service.all_games
        ])

    async def players(self, request) -> web.Response:
        return web.json_response([
            player.to_dict()
            for player in self.player_service.all_players
        ])
