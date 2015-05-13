#!/usr/bin/env python3
"""
Usage:
    server.py [--nodb | --db TYPE]

Options:
    --nodb      Don't use a database (Use a mock.Mock). Caution: Will break things.
    --db TYPE   Use TYPE database driver [default: QMYSQL]
"""

import asyncio

import sys
import logging
from logging import handlers
import signal
import aiomysql

from quamash import QEventLoop
from PySide import QtSql, QtCore
from PySide.QtCore import QTimer

from passwords import PRIVATE_KEY, DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_TABLE
from server.games_service import GamesService

from server.players import *
import config

import server

if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    try:
        def signal_handler(signal, frame):
            logger.info("Received signal, shutting down")
            if not done.done():
                done.set_result(0)
            loop.stop()

        app = QtCore.QCoreApplication(sys.argv)

        if config.LIBRARY_PATH:
            app.addLibraryPath(config.LIBRARY_PATH)

        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)

        done = asyncio.Future()

        from docopt import docopt
        args = docopt(__doc__, version='FAF Server')

        rootlogger = logging.getLogger("")
        logHandler = handlers.RotatingFileHandler(config.LOG_PATH + "server.log", backupCount=1024, maxBytes=16777216)
        logFormatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s')
        logHandler.setFormatter(logFormatter)
        rootlogger.addHandler(logHandler)
        rootlogger.setLevel(config.LOG_LEVEL)

        players_online = PlayersOnline()

        if args['--nodb']:
            from unittest import mock
            db = mock.Mock()
        else:
            db = QtSql.QSqlDatabase(args['--db'])
            db.setHostName(DB_SERVER)
            db.setPort(DB_PORT)

            db.setDatabaseName(DB_TABLE)
            db.setUserName(DB_LOGIN)
            db.setPassword(DB_PASSWORD)
            db.setConnectOptions("MYSQL_OPT_RECONNECT=1")

        privkey = PRIVATE_KEY

        if not db.open():
            logger.error(db.lastError().text())
            sys.exit(1)

        # Make sure we can shutdown gracefully
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        def poll_signal():
            pass
        timer = QTimer()
        timer.timeout.connect(poll_signal)
        timer.start(200)

        dirtyGameList = []
        games = GamesService(players_online, db)

        db_pool = loop.run_until_complete(aiomysql.create_pool(host=DB_SERVER, port=DB_PORT,
                                                               user=DB_LOGIN, password=DB_PASSWORD,
                                                               db=DB_TABLE))

        lobby_server = loop.run_until_complete(
            server.run_lobby_server(('', 8001),
                                    players_online,
                                    games,
                                    db,
                                    db_pool,
                                    loop)
        )
        nat_packet_server, game_server = \
            server.run_game_server(('', 8000),
                                   players_online,
                                   games,
                                   db,
                                   db_pool,
                                   loop)
        game_server = loop.run_until_complete(game_server)

        loop.run_until_complete(done)

    except Exception as ex:
        logger.exception("Failure booting server {}".format(ex))
