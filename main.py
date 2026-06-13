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
import signal
import sys
import time
from functools import wraps

import humanize
from docopt import docopt
from prometheus_client import start_http_server

import server
from server import info
from server.config import config
from server.control import ControlServer
from server.db import FAFDatabase, get_and_validate_database_version
from server.game_service import GameService
from server.health import HealthServer
from server.player_service import PlayerService
from server.profiler import Profiler
from server.timing import datetime_now


def log_signal(func):
    @wraps(func)
    def wrapped(sig, frame):
        logger.info("Received signal %s", signal.Signals(sig))
        return func(sig, frame)

    return wrapped


async def main():
    global shutdown_time

    logger.info(
        "Lobby %s (Python %s) on %s named %s",
        info.VERSION,
        info.PYTHON_VERSION,
        sys.platform,
        info.CONTAINER_NAME,
    )

    if config.ENABLE_METRICS:
        logger.info("Using prometheus on port: %i", config.METRICS_PORT)
        start_http_server(config.METRICS_PORT)

    loop = asyncio.get_running_loop()
    done = loop.create_future()

    logger.info("Event loop: %s", loop)

    @log_signal
    def done_handler(sig: int, frame):
        if not done.done():
            done.set_result(0)

    # Make sure we can shutdown gracefully
    signal.signal(signal.SIGTERM, done_handler)
    signal.signal(signal.SIGINT, done_handler)

    database = FAFDatabase(
        host=config.DB_SERVER,
        port=int(config.DB_PORT),
        user=config.DB_LOGIN,
        password=config.DB_PASSWORD,
        db=config.DB_NAME,
    )
    database_version = await get_and_validate_database_version(database)
    logger.info(
        "Database version is %s",
        f"v{database_version}" if database_version is not None else "unknown",
    )

    # Set up services

    instance = server.ServerInstance(
        "LobbyServer",
        database,
        loop
    )
    player_service: PlayerService = instance.services["player_service"]
    game_service: GameService = instance.services["game_service"]

    profiler = Profiler(player_service)
    await profiler.refresh()
    config.register_callback("PROFILING_COUNT", profiler.refresh)
    config.register_callback("PROFILING_DURATION", profiler.refresh)
    config.register_callback("PROFILING_INTERVAL", profiler.refresh)

    health_server = HealthServer(instance)
    await health_server.run_from_config()
    config.register_callback(
        "HEALTH_SERVER_PORT",
        health_server.run_from_config
    )

    control_server = ControlServer(instance)
    await control_server.run_from_config()
    config.register_callback(
        "CONTROL_SERVER_PORT",
        control_server.run_from_config
    )

    await instance.start_services()

    try:
        await instance.listen(
            address=(config.WS_HOST, config.WS_PORT),
            path=config.WS_PATH,
        )
    except Exception as e:
        raise RuntimeError(
            f"Error starting WebSocket listener on "
            f"{config.WS_HOST}:{config.WS_PORT}{config.WS_PATH}"
        ) from e

    server.metrics.info.info({
        "version": info.VERSION,
        "python_version": info.PYTHON_VERSION,
        "start_time": datetime_now().strftime("%m-%d %H:%M"),
        "game_uid": str(game_service.game_id_counter)
    })
    logger.info(
        "Server started in %0.2f seconds",
        time.perf_counter() - startup_time
    )

    exit_code = await done

    shutdown_time = time.perf_counter()

    # Cleanup
    await instance.graceful_shutdown()

    drain_task = asyncio.create_task(instance.drain())

    @log_signal
    def drain_handler(sig: int, frame):
        if not drain_task.done():
            drain_task.cancel()

    # Allow us to force shut down by skipping the drain
    signal.signal(signal.SIGTERM, drain_handler)
    signal.signal(signal.SIGINT, drain_handler)

    await drain_task
    await instance.shutdown()
    await control_server.shutdown()
    await database.close()

    # Health server should be the last thing to shut down
    await health_server.shutdown()

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
        humanize.precisedelta(int(stop_time - startup_time))
    )

    if shutdown_time is not None:
        logger.info(
            "Server shut down in %0.2f seconds",
            stop_time - shutdown_time
        )

    if exit_code:
        logger.error("Server shut down with exit code: %s", exit_code)

    exit(exit_code)
