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
import os
import signal
import socket
import sys
from datetime import datetime

import server
from server.config import config
from docopt import docopt
from server.api.api_accessor import ApiAccessor
from server.core import create_services
from server.ice_servers.nts import TwilioNTS
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
        host=config.DB_SERVER,
        port=int(config.DB_PORT),
        user=config.DB_LOGIN,
        password=config.DB_PASSWORD,
        maxsize=10,
        db=config.DB_NAME,
    )

    # Set up services

    twilio_nts = None
    if config.TWILIO_ACCOUNT_SID:
        twilio_nts = TwilioNTS()
    else:
        logger.warning(
            "Twilio is not set up. You must set TWILIO_ACCOUNT_SID and TWILIO_TOKEN to use the Twilio ICE servers."
        )

    api_accessor = None
    if config.USE_API:
        api_accessor = ApiAccessor()

    services = create_services({
        "api_accessor": api_accessor,
        "database": database,
        "loop": loop,
    })

    await asyncio.gather(*[
        service.initialize() for service in services.values()
    ])

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

            if len(services["player_service"]) > 1000:
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

    ctrl_server = await server.run_control_server(
        services["player_service"],
        services["game_service"]
    )

    lobby_server = await server.run_lobby_server(
        address=('', 8001),
        database=database,
        geoip_service=services["geo_ip_service"],
        player_service=services["player_service"],
        game_service=services["game_service"],
        nts_client=twilio_nts,
        ladder_service=services["ladder_service"],
        loop=loop
    )

    for sock in lobby_server.sockets:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    server.metrics.info.info({
        "version": os.environ.get("VERSION") or "dev",
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "start_time": datetime.utcnow().strftime("%m-%d %H:%M"),
        "game_uid": str(services["game_service"].game_id_counter)
    })

    await done

    # Cleanup
    await asyncio.gather(*[
        service.shutdown() for service in services.values()
    ])
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
