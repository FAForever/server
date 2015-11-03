"""
Tiny local-only http server for getting stats and performing various tasks
"""

import asyncio
import json

from aiohttp import web
import logging
from server import PlayerService, GameService, LobbyConnection

logger = logging.getLogger(__name__)


class ControlServer:
    def __init__(self, game_service: GameService, player_service: PlayerService):
        self.game_service = game_service
        self.player_service = player_service

    def games(self, request):
        body = repr(self.game_service.live_games).encode()
        return web.Response(body=body)

    def players(self, request):
        body = json.dumps({
            'data': list(map(lambda p: p.to_dict(), self.player_service.players.values()))
        })
        return web.Response(body=body.encode())

    async def kick_player(self, request):
        player = self.player_service.players[int(request.match_info.get('player_id'))]
        assert isinstance(player.lobby_connection, LobbyConnection)
        player.lobby_connection.kick("test")
        return web.Response()

@asyncio.coroutine
def init(loop, player_service, game_service):
    """
    Initialize the http control server
    """
    ctrl_server = ControlServer(game_service, player_service)
    app = web.Application(loop=loop)
    app.router.add_route('GET', '/games', ctrl_server.games)
    app.router.add_route('GET', '/players', ctrl_server.players)
    app.router.add_route('POST', '/players/{player_id}', ctrl_server.kick_player)

    srv = yield from loop.create_server(app.make_handler(), '127.0.0.1', '4040')
    logger.info("Control server listening on http://127.0.0.1:4040")
    return srv
