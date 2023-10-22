"""
Kubernetes compatible HTTP health check server.
"""

import http
import socket

from aiohttp import web

from .config import config
from .decorators import with_logger


@with_logger
class HealthServer:
    def __init__(
        self,
        lobby_server: "ServerInstance",
    ):
        self.lobby_server = lobby_server
        self.host = None
        self.port = None

        self.app = web.Application()
        self.runner = web.AppRunner(self.app, access_log=None)

        self.app.add_routes([
            web.get("/ready", self.ready)
        ])

    async def run_from_config(self) -> None:
        """
        Initialize the http health server
        """
        host = socket.gethostbyname(socket.gethostname())
        port = config.HEALTH_SERVER_PORT

        await self.shutdown()
        await self.start(host, port)

    async def start(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        self._logger.info(
            "Health server listening on http://%s:%s", host, port
        )

    async def shutdown(self) -> None:
        await self.runner.cleanup()
        self.host = None
        self.port = None

    async def ready(self, request):
        code_map = {
            True: http.HTTPStatus.OK.value,
            False: http.HTTPStatus.SERVICE_UNAVAILABLE.value
        }

        return web.Response(
            status=code_map[self.lobby_server.started],
            content_type="text/plain"
        )
