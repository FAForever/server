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
from datetime import datetime
from functools import wraps

import humanize
from docopt import docopt
from prometheus_client import start_http_server

import server
from server import info
from server.config import config
from server.control import ControlServer
from server.game_service import GameService
from server.health import HealthServer
from server.player_service import PlayerService
from server.profiler import Profiler
from server.protocol import QDataStreamProtocol, SimpleJsonProtocol


def log_signal(func):
    @wraps(func)
    def wrapped(sig, frame):
        logger.info("Received signal %s", signal.Signals(sig))
        return func(sig, frame)

    return wrapped


async def main():
    global startup_time, shutdown_time

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

    database = server.db.FAFDatabase(
        host=config.DB_SERVER,
        port=int(config.DB_PORT),
        user=config.DB_LOGIN,
        password=config.DB_PASSWORD,
        db=config.DB_NAME
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
    profiler.refresh()
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
        "version": info.VERSION,
        "python_version": info.PYTHON_VERSION,
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
        humanize.precisedelta(stop_time - startup_time)
    )

    if shutdown_time is not None:
        logger.info(
            "Server shut down in %0.2f seconds",
            stop_time - shutdown_time
        )

    if exit_code:
        logger.error("Server shut down with exit code: %s", exit_code)

    exit(exit_code)
