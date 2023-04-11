"""
Tiny http server for introspecting state
"""

import http
import socket
from json import dumps

from aiohttp import web

from .config import config
from .decorators import with_logger


@with_logger
class ControlServer:
    def __init__(
        self,
        lobby_server: "ServerInstance",
        host: str,
        port: int
    ):
        self.lobby_server = lobby_server
        self.game_service = lobby_server.services["game_service"]
        self.player_service = lobby_server.services["player_service"]
        self.host = host
        self.port = port

        self.app = web.Application()
        self.runner = web.AppRunner(self.app)

        self.app.add_routes([
            web.get("/games", self.games),
            web.get("/players", self.players),
            # Healthcheck endpoints
            web.get("/ready", self.ready)
        ])

    async def start(self) -> None:
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        self._logger.info(
            "Control server listening on http://%s:%s", self.host, self.port
        )

    async def shutdown(self) -> None:
        await self.runner.cleanup()

    async def games(self, request):
        body = dumps(to_dict_list(self.game_service.all_games))
        return web.Response(body=body.encode(), content_type="application/json")

    async def players(self, request):
        body = dumps(to_dict_list(self.player_service.all_players))
        return web.Response(body=body.encode(), content_type="application/json")

    async def ready(self, request):
        code_map = {
            True: http.HTTPStatus.OK.value,
            False: http.HTTPStatus.SERVICE_UNAVAILABLE.value
        }

        return web.Response(
            status=code_map[self.lobby_server.started]
        )


async def run_control_server(lobby_server: "ServerInstance") -> ControlServer:
    """
    Initialize the http control server
    """
    host = socket.gethostbyname(socket.gethostname())
    port = config.CONTROL_SERVER_PORT

    ctrl_server = ControlServer(lobby_server, host, port)
    await ctrl_server.start()

    return ctrl_server


def to_dict_list(list_):
    return list(map(lambda p: p.to_dict(), list_))
