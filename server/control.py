"""
Tiny local-only http server for getting stats and performing various tasks
"""

import asyncio
from aiohttp import web
import logging
from server import PlayerService, GameService

logger = logging.getLogger(__name__)

def make_handler(player_service: PlayerService, game_service: GameService):
    @asyncio.coroutine
    def handler(request):
        body = """
Users ({}):
{}
Games ({}):
{}
    """.format(len(player_service.players),
               player_service.players,
               len(game_service.live_games),
               game_service.live_games)
        return web.Response(body=body.encode('utf-8'))
    return handler

@asyncio.coroutine
def init(loop, player_service, game_service):
    """
    Initialize the http control server
    """
    app = web.Application(loop=loop)
    app.router.add_route('GET', '/', make_handler(player_service, game_service))

    srv = yield from loop.create_server(app.make_handler(), '127.0.0.1', '4040')
    logger.info("Control server listening on http://127.0.0.1:4040")
    return srv
