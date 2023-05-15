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
from server.config import config
from server.game_service import GameService
from server.ice_servers.nts import TwilioNTS
from server.player_service import PlayerService
from server.profiler import Profiler
from server.protocol import QDataStreamProtocol, SimpleJsonProtocol


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

    instance = server.ServerInstance(
        "LobbyServer",
        database,
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

    PROTO_CLASSES = {
        QDataStreamProtocol.__name__: QDataStreamProtocol,
        SimpleJsonProtocol.__name__: SimpleJsonProtocol
    }
    for cfg in config.LISTEN:
        try:
            host = cfg["ADDRESS"]
            port = cfg["PORT"]
            proto_class_name = cfg["PROTOCOL"]
            name = cfg.get("NAME")
            proxy = cfg.get("PROXY", False)

            proto_class = PROTO_CLASSES[proto_class_name]

            await instance.listen(
                address=(host, port),
                name=name,
                protocol_class=proto_class,
                proxy=proxy
            )
        except Exception as e:
            raise RuntimeError(f"Error with server instance config: {cfg}") from e

    if not instance.contexts:
        raise RuntimeError(
            "The server was not configured to listen on any ports! Check the "
            "config file and try again."
        )

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

    exit_code = await done

    shutdown_time = time.perf_counter()

    # Cleanup
    await instance.shutdown()
    await ctrl_server.shutdown()

    # Close DB connections
    await database.close()

    return exit_code


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
    logger.setLevel(logging.INFO)

    config.refresh()
    logger.setLevel(config.LOG_LEVEL)

    if config.USE_UVLOOP:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    exit_code = asyncio.run(main())

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

    if exit_code:
        logger.error("Server shut down with exit code: %s", exit_code)

    exit(exit_code)
