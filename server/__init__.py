"""
Forged Alliance Forever server project

Copyright (c) 2012-2014 Gael Honorez
Copyright (c) 2015-2016 Michael Søndergaard <sheeo@faforever.com>

Distributed under GPLv3, see license.txt
"""
import logging
from typing import Optional

from prometheus_client import start_http_server
import asyncio

from server.db import FAFDatabase
from . import config as config
from .games.game import GameState, VisibilityState
from .stats.game_stats_service import GameStatsService
from .gameconnection import GameConnection
from .ice_servers.nts import TwilioNTS
from .lobbyconnection import LobbyConnection
from .protocol import QDataStreamProtocol
from .servercontext import ServerContext
from .geoip_service import GeoIpService
from .player_service import PlayerService
from .game_service import GameService
from .ladder_service import LadderService
from .control import init as run_control_server
from .timing import at_interval


__version__ = '0.9.17'
__author__ = 'Askaholic, Chris Kitching, Dragonfire, Gael Honorez, Jeroen De Dauw, Crotalus, Michael Søndergaard, Michel Jung'
__contact__ = 'admin@faforever.com'
__license__ = 'GPLv3'
__copyright__ = 'Copyright (c) 2011-2015 ' + __author__

__all__ = (
    'GameConnection',
    'GameStatsService',
    'GameService',
    'LadderService',
    'run_lobby_server',
    'run_control_server',
    'games',
    'control',
    'abc',
    'protocol'
)

DIRTY_REPORT_INTERVAL = 1  # Seconds
stats = None

if config.ENABLE_METRICS:
    start_http_server(config.METRICS_PORT)


def encode_message(message: str):
    # Crazy evil encoding scheme
    return QDataStreamProtocol.pack_message(message)


def run_lobby_server(
    address: (str, int),
    database: FAFDatabase,
    player_service: PlayerService,
    games: GameService,
    loop,
    nts_client: Optional[TwilioNTS],
    geoip_service: GeoIpService,
    ladder_service: LadderService
) -> ServerContext:
    """
    Run the lobby server
    """

    @at_interval(DIRTY_REPORT_INTERVAL)
    async def do_report_dirties():
        games.update_active_game_metrics()
        dirty_games = games.dirty_games
        dirty_queues = games.dirty_queues
        dirty_players = player_service.dirty_players
        games.clear_dirty()
        player_service.clear_dirty()

        tasks = []
        if dirty_queues:
            tasks.append(
                ctx.broadcast({
                        'command': 'matchmaker_info',
                        'queues': [queue.to_dict() for queue in dirty_queues]
                    },
                    lambda lobby_conn: lobby_conn.authenticated
                )
            )

        if dirty_players:
            tasks.append(
                ctx.broadcast({
                        'command': 'player_info',
                        'players': [player.to_dict() for player in dirty_players]
                    },
                    lambda lobby_conn: lobby_conn.authenticated
                )
            )

        # TODO: This spams squillions of messages: we should implement per-
        # connection message aggregation at the next abstraction layer down :P
        for game in dirty_games:
            if game.state == GameState.ENDED:
                games.remove_game(game)

            # So we're going to be broadcasting this to _somebody_...
            message = game.to_dict()

            # These games shouldn't be broadcast, but instead privately sent
            # to those who are allowed to see them.
            if game.visibility == VisibilityState.FRIENDS:
                # To see this game, you must have an authenticated
                # connection and be a friend of the host, or the host.
                def validation_func(lobby_conn):
                    return lobby_conn.player.id in game.host.friends or \
                           lobby_conn.player == game.host
            else:
                def validation_func(lobby_conn):
                    return lobby_conn.player.id not in game.host.foes

            tasks.append(ctx.broadcast(
                message,
                lambda lobby_conn: lobby_conn.authenticated and validation_func(lobby_conn)
            ))

        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logging.getLogger().exception(e)

    ping_msg = encode_message('PING')

    @at_interval(45)
    async def ping_broadcast():
        await ctx.broadcast_raw(ping_msg)

    def make_connection() -> LobbyConnection:
        return LobbyConnection(
            database=database,
            geoip=geoip_service,
            games=games,
            nts_client=nts_client,
            players=player_service,
            ladder_service=ladder_service
        )

    ctx = ServerContext(make_connection, name="LobbyServer")
    loop.run_until_complete(ctx.listen(*address))
    return ctx
