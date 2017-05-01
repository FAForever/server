#!/usr/bin/env python3
"""
Usage:
    server.py [--nodb | --db TYPE]

Options:
    --nodb      Don't use a database (Use a mock.Mock). Caution: Will break things.
    --db TYPE   Use TYPE database driver [default: QMYSQL]
"""

import asyncio

import logging
from logging import handlers
import signal
import socket

from server.game_service import GameService
from server.matchmaker import MatchmakerQueue
from server.player_service import PlayerService
from server.natpacketserver import NatPacketServer
from server.stats.game_stats_service import GameStatsService, EventService, AchievementService
from server.api.api_accessor import ApiAccessor
import server
import server.config as config
from server.config import DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_NAME

if __name__ == '__main__':
    logger = logging.getLogger()
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(logging.Formatter('%(levelname)-8s %(name)-30s %(message)s'))
    logger.addHandler(stderr_handler)
    logger.setLevel(logging.DEBUG)

    try:
        def signal_handler(signal, frame):
            logger.info("Received signal, shutting down")
            if not done.done():
                done.set_result(0)

        loop = asyncio.get_event_loop()
        done = asyncio.Future()

        from docopt import docopt
        args = docopt(__doc__, version='FAF Server')

        logger.info("Using StatsD server: ".format(config.STATSD_SERVER))

        # Make sure we can shutdown gracefully
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        pool_fut = asyncio.async(server.db.connect(host=DB_SERVER,
                                                   port=int(DB_PORT),
                                                   user=DB_LOGIN,
                                                   password=DB_PASSWORD,
                                                   maxsize=10,
                                                   db=DB_NAME,
                                                   loop=loop))
        db_pool = loop.run_until_complete(pool_fut)

        players_online = PlayerService(db_pool)
        api_accessor = ApiAccessor()
        event_service = EventService(api_accessor)
        achievement_service = AchievementService(api_accessor)
        game_stats_service = GameStatsService(event_service, achievement_service)

        natpacket_server = NatPacketServer(addresses=config.LOBBY_NAT_ADDRESSES, loop=loop)
        loop.run_until_complete(natpacket_server.listen())
        server.NatPacketServer.instance = natpacket_server

        games = GameService(players_online, game_stats_service)
        matchmaker_queue = MatchmakerQueue('ladder1v1', players_online, games)
        players_online.ladder_queue = matchmaker_queue

        ctrl_server = loop.run_until_complete(server.run_control_server(loop, players_online, games))

        lobby_server = server.run_lobby_server(('', 8001),
                                    players_online,
                                    games,
                                    loop)

        for sock in lobby_server.sockets:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        loop.run_until_complete(done)
        players_online.broadcast_shutdown()
        loop.close()

    except Exception as ex:
        logger.exception("Failure booting server {}".format(ex))
