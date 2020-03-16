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
from server.timing import at_interval


async def main():
    loop = asyncio.get_running_loop()
    done = asyncio.Future()

    def signal_handler(sig: int, _frame):
        logger.info(
            "Received signal %s, shutting down",
            signal.Signals(sig)
        )
        if not done.done():
            done.set_result(0)

    # Make sure we can shutdown gracefully
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    if config.ENABLE_METRICS:
        logger.info("Using prometheus on port: {}".format(config.METRICS_PORT))

    database = server.db.FAFDatabase(loop)
    await database.connect(
        host=DB_SERVER,
        port=int(DB_PORT),
        user=DB_LOGIN,
        password=DB_PASSWORD,
        maxsize=10,
        db=DB_NAME,
    )

    # Set up services

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

    player_service = PlayerService(database)
    geoip_service = GeoIpService()

    event_service = EventService(api_accessor)
    achievement_service = AchievementService(api_accessor)
    game_stats_service = GameStatsService(
        event_service, achievement_service
    )

    game_service = GameService(database, player_service, game_stats_service)
    ladder_service = LadderService(database, game_service)

    await asyncio.gather(
        player_service.initialize(),
        game_service.initialize(),
        ladder_service.initialize(),
        geoip_service.initialize()
    )

    if config.PROFILING_INTERVAL > 0:
        logger.warning("Profiling enabled! This will create additional load.")
        import cProfile
        pr = cProfile.Profile()
        profiled_count = 0
        max_count = 300

        @at_interval(config.PROFILING_INTERVAL, loop=loop)
        async def run_profiler():
            nonlocal profiled_count
            nonlocal pr

            if len(player_service) > 1000:
                return
            elif profiled_count >= max_count:
                del pr
                return

            logger.info("Starting profiler")
            pr.enable()
            await asyncio.sleep(2)
            pr.disable()
            profiled_count += 1

            logging.info("Done profiling %i/%i", profiled_count, max_count)
            pr.dump_stats("profile.txt")

    ctrl_server = await server.run_control_server(player_service, game_service)

    lobby_server = await server.run_lobby_server(
        address=('', 8001),
        database=database,
        geoip_service=geoip_service,
        player_service=player_service,
        game_service=game_service,
        nts_client=twilio_nts,
        ladder_service=ladder_service,
        loop=loop
    )

    for sock in lobby_server.sockets:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    await done

    # Cleanup
    ladder_service.shutdown_queues()
    await player_service.broadcast_shutdown()
    await ctrl_server.shutdown()

    # Close DB connections
    await database.close()


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

    asyncio.run(main())
