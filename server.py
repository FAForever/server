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
import signal
import socket

import server
import server.config as config
from docopt import docopt
from server.api.api_accessor import ApiAccessor
from server.config import (
    DB_LOGIN, DB_NAME, DB_PASSWORD, DB_PORT, DB_SERVER, TWILIO_ACCOUNT_SID
)
from server.game_service import GameService
from server.geoip_service import GeoIpService
from server.ice_servers.nts import TwilioNTS
from server.ladder_service import LadderService
from server.player_service import PlayerService
from server.stats.game_stats_service import (
    AchievementService, EventService, GameStatsService
)

if __name__ == '__main__':
    args = docopt(__doc__, version='FAF Server')

    logger = logging.getLogger()
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(
        logging.Formatter(
            fmt='%(levelname)-8s %(asctime)s %(name)-30s %(message)s',
            datefmt='%b %d  %H:%M:%S'
        )
    )
    logger.addHandler(stderr_handler)
    logger.setLevel(config.LOG_LEVEL)

    try:
        loop = asyncio.get_event_loop()
        done = asyncio.Future()

        def signal_handler(_sig, _frame):
            logger.info("Received signal, shutting down")
            if not done.done():
                done.set_result(0)

        if config.ENABLE_STATSD:
            logger.info("Using StatsD server: ".format(config.STATSD_SERVER))

        # Make sure we can shutdown gracefully
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        database = server.db.FAFDatabase(loop)
        db_fut = asyncio.ensure_future(
            database.connect(
                host=DB_SERVER,
                port=int(DB_PORT),
                user=DB_LOGIN,
                password=DB_PASSWORD,
                maxsize=10,
                db=DB_NAME,
            )
        )
        loop.run_until_complete(db_fut)

        players_online = PlayerService(database)

        twilio_nts = None
        if TWILIO_ACCOUNT_SID:
            twilio_nts = TwilioNTS()
        else:
            logger.warning(
                "Twilio is not set up. You must set TWILIO_ACCOUNT_SID and TWILIO_TOKEN to use the Twilio ICE servers."
            )

        api_accessor = None
        if config.USE_API:
            api_accessor = ApiAccessor()

        event_service = EventService(api_accessor)
        achievement_service = AchievementService(api_accessor)
        game_stats_service = GameStatsService(
            event_service, achievement_service
        )

        games = GameService(database, players_online, game_stats_service)
        ladder_service = LadderService(database, games)

        ctrl_server = loop.run_until_complete(
            server.run_control_server(loop, players_online, games)
        )

        lobby_server = server.run_lobby_server(
            address=('', 8001),
            database=database,
            geoip_service=GeoIpService(),
            player_service=players_online,
            games=games,
            nts_client=twilio_nts,
            ladder_service=ladder_service,
            loop=loop
        )

        for sock in lobby_server.sockets:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        loop.run_until_complete(done)
        players_online.broadcast_shutdown()
        ladder_service.shutdown_queues()

        # Close DB connections
        loop.run_until_complete(database.close())

        loop.close()

    except Exception as ex:
        logger.exception("Failure booting server {}".format(ex))
