"""
Tiny local-only http server for getting stats and performing various tasks
"""

import socket
from json import dumps

from aiohttp import web

from . import config
from .decorators import with_logger
from .game_service import GameService
from .player_service import PlayerService


@with_logger
class ControlServer:
    def __init__(
        self,
        game_service: GameService,
        player_service: PlayerService,
        host: str,
        port: int
    ):
        self.game_service = game_service
        self.player_service = player_service
        self.host = host
        self.port = port

        self.app = web.Application()
        self.runner = web.AppRunner(self.app)

        self.app.add_routes([
            web.get("/games", self.games),
            web.get("/players", self.players)
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
        return web.Response(body=body.encode(), content_type='application/json')

    async def players(self, request):
        body = dumps(to_dict_list(self.player_service.all_players))
        return web.Response(body=body.encode(), content_type='application/json')


async def run_control_server(
    player_service: PlayerService,
    game_service: GameService
) -> ControlServer:
    """
    Initialize the http control server
    """
    host = socket.gethostbyname(socket.gethostname())
    port = config.CONTROL_SERVER_PORT

    ctrl_server = ControlServer(game_service, player_service, host, port)
    await ctrl_server.start()

    return ctrl_server


def to_dict_list(list_):
    return list(map(lambda p: p.to_dict(), list_))
