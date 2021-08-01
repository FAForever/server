#!/usr/bin/env python3
"""
Usage:
    server.py [--configuration-file FILE]

Options:
    --configuration-file FILE    Load config variables from FILE
"""

import asyncio
import logging
import os
import platform
import signal
import sys
import time
from datetime import datetime

import humanize
from docopt import docopt

import server
from server.api.api_accessor import ApiAccessor
from server.config import config
from server.game_service import GameService
from server.ice_servers.nts import TwilioNTS
from server.player_service import PlayerService
from server.profiler import Profiler


async def main():
    global startup_time, shutdown_time

    version = os.environ.get("VERSION") or "dev"
    python_version = platform.python_version()

    logger.info(
        "Lobby %s (Python %s) on %s",
        version,
        python_version,
        sys.platform
    )

    loop = asyncio.get_running_loop()
    done = loop.create_future()

    logger.info("Event loop: %s", loop)

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

    database = server.db.FAFDatabase(
        host=config.DB_SERVER,
        port=int(config.DB_PORT),
        user=config.DB_LOGIN,
        password=config.DB_PASSWORD,
        db=config.DB_NAME
    )

    # Set up services

    twilio_nts = None
    if config.TWILIO_ACCOUNT_SID:
        twilio_nts = TwilioNTS()
    else:
        logger.warning(
            "Twilio is not set up. You must set TWILIO_ACCOUNT_SID and TWILIO_TOKEN to use the Twilio ICE servers."
        )

    api_accessor = ApiAccessor()

    instance = server.ServerInstance(
        "LobbyServer",
        database,
        api_accessor,
        twilio_nts,
        loop
    )
    player_service: PlayerService = instance.services["player_service"]
    game_service: GameService = instance.services["game_service"]

    profiler = Profiler(player_service)
    profiler.refresh()
    config.register_callback("PROFILING_COUNT", profiler.refresh)
    config.register_callback("PROFILING_DURATION", profiler.refresh)
    config.register_callback("PROFILING_INTERVAL", profiler.refresh)

    await instance.start_services()

    ctrl_server = await server.run_control_server(player_service, game_service)

    async def restart_control_server():
        nonlocal ctrl_server

        await ctrl_server.shutdown()
        ctrl_server = await server.run_control_server(
            player_service,
            game_service
        )
    config.register_callback("CONTROL_SERVER_PORT", restart_control_server)

    await instance.listen(("", 8002))

    server.metrics.info.info({
        "version": version,
        "python_version": python_version,
        "start_time": datetime.utcnow().strftime("%m-%d %H:%M"),
        "game_uid": str(game_service.game_id_counter)
    })
    logger.info(
        "Server started in %0.2f seconds",
        time.perf_counter() - startup_time
    )

    await done

    shutdown_time = time.perf_counter()

    # Cleanup
    await instance.shutdown()
    await ctrl_server.shutdown()

    # Close DB connections
    await database.close()


if __name__ == "__main__":
    startup_time = time.perf_counter()
    shutdown_time = None

    args = docopt(__doc__, version="FAF Server")
    config_file = args.get("--configuration-file")
    if config_file:
        os.environ["CONFIGURATION_FILE"] = config_file

    logger = logging.getLogger()
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(
        logging.Formatter(
            fmt="%(levelname)-8s %(asctime)s %(name)-30s %(message)s",
            datefmt="%b %d  %H:%M:%S"
        )
    )
    logger.addHandler(stderr_handler)
    logger.setLevel(config.LOG_LEVEL)

    if config.USE_UVLOOP:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    asyncio.run(main())

    stop_time = time.perf_counter()
    logger.info(
        "Total server uptime: %s",
        humanize.naturaldelta(stop_time - startup_time)
    )

    if shutdown_time is not None:
        logger.info(
            "Server shut down in %0.2f seconds",
            stop_time - shutdown_time
        )
