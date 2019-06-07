"""
Tiny local-only http server for getting stats and performing various tasks
"""

import socket

from aiohttp import web
import logging
from server import PlayerService, GameService, config
from json import dumps

logger = logging.getLogger(__name__)


class ControlServer:
    def __init__(self, game_service: GameService, player_service: PlayerService):
        self.game_service = game_service
        self.player_service = player_service

    def games(self, request):
        body = dumps(to_dict_list(self.game_service.all_games))
        return web.Response(body=body.encode(), content_type='application/json')

    def players(self, request):
        body = dumps(to_dict_list(self.player_service.players.values()))
        return web.Response(body=body.encode(), content_type='application/json')


async def init(loop, player_service, game_service):
    """
    Initialize the http control server
    """
    ctrl_server = ControlServer(game_service, player_service)
    app = web.Application(loop=loop)
    app.router.add_route('GET', '/games', ctrl_server.games)
    app.router.add_route('GET', '/players', ctrl_server.players)

    address = socket.gethostbyname(socket.gethostname())
    port = config.CONTROL_SERVER_PORT

    srv = await loop.create_server(app.make_handler(), address, port)
    logger.info("Control server listening on http://%s:%s", address, port)
    return srv


def to_dict_list(list_):
    return list(map(lambda p: p.to_dict(), list_))
