"""
Forged Alliance Forever server project

Copyright (c) 2012-2014 Gael Honorez
Copyright (c) 2015-2016 Michael Søndergaard <sheeo@faforever.com>

Distributed under GPLv3, see license.txt
"""
import logging
from typing import Optional, Tuple, Type

from prometheus_client import start_http_server

from server.db import FAFDatabase

from .config import config
from .configuration_service import ConfigurationService
from .control import run_control_server
from .game_service import GameService
from .gameconnection import GameConnection
from .games import GameState, VisibilityState
from .geoip_service import GeoIpService
from .ice_servers.nts import TwilioNTS
from .ladder_service import LadderService
from .lobbyconnection import LobbyConnection
from .message_queue_service import MessageQueueService
from .player_service import PlayerService
from .protocol import Protocol, QDataStreamProtocol
from .rating_service.rating_service import RatingService
from .servercontext import ServerContext
from .stats.game_stats_service import GameStatsService
from .timing import at_interval

__author__ = 'Askaholic, Chris Kitching, Dragonfire, Gael Honorez, Jeroen De Dauw, Crotalus, Michael Søndergaard, Michel Jung'
__contact__ = 'admin@faforever.com'
__license__ = 'GPLv3'
__copyright__ = 'Copyright (c) 2011-2015 ' + __author__

__all__ = (
    'GameConnection',
    'GameStatsService',
    'GameService',
    'LadderService',
    'RatingService',
    'run_lobby_server',
    'run_control_server',
    'game_service',
    'control',
    'abc',
    'protocol',
    'ConfigurationService',
    'MessageQueueService',
    'RatingService'
)

DIRTY_REPORT_INTERVAL = 1  # Seconds
stats = None
logger = logging.getLogger("server")

if config.ENABLE_METRICS:
    logger.info("Using prometheus on port: %i", config.METRICS_PORT)
    start_http_server(config.METRICS_PORT)


async def run_lobby_server(
    address: Tuple[str, int],
    database: FAFDatabase,
    player_service: PlayerService,
    game_service: GameService,
    nts_client: Optional[TwilioNTS],
    geoip_service: GeoIpService,
    ladder_service: LadderService,
    loop,
    protocol_class: Type[Protocol] = QDataStreamProtocol,
) -> ServerContext:
    """
    Run the lobby server
    """

    @at_interval(DIRTY_REPORT_INTERVAL, loop=loop)
    async def do_report_dirties():
        game_service.update_active_game_metrics()
        dirty_games = game_service.dirty_games
        dirty_queues = game_service.dirty_queues
        dirty_players = player_service.dirty_players
        game_service.clear_dirty()
        player_service.clear_dirty()

        try:
            if dirty_queues:
                ctx.write_broadcast({
                        'command': 'matchmaker_info',
                        'queues': [queue.to_dict() for queue in dirty_queues]
                    },
                    lambda lobby_conn: lobby_conn.authenticated
                )
        except Exception:
            logger.exception("Error writing matchmaker_info")

        try:
            if dirty_players:
                ctx.write_broadcast({
                        'command': 'player_info',
                        'players': [player.to_dict() for player in dirty_players]
                    },
                    lambda lobby_conn: lobby_conn.authenticated
                )
        except Exception:
            logger.exception("Error writing player_info")

        # TODO: This spams squillions of messages: we should implement per-
        # connection message aggregation at the next abstraction layer down :P
        for game in dirty_games:
            try:
                if game.state == GameState.ENDED:
                    game_service.remove_game(game)

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

                ctx.write_broadcast(
                    message,
                    lambda lobby_conn: lobby_conn.authenticated and validation_func(lobby_conn)
                )
            except Exception:
                logger.exception("Error writing game_info %s", game.id)

    ping_msg = protocol_class.encode_message({"command": "ping"})

    @at_interval(45, loop=loop)
    def ping_broadcast():
        ctx.write_broadcast_raw(ping_msg)

    def make_connection() -> LobbyConnection:
        return LobbyConnection(
            database=database,
            geoip=geoip_service,
            game_service=game_service,
            nts_client=nts_client,
            players=player_service,
            ladder_service=ladder_service
        )

    ctx = ServerContext("LobbyServer", make_connection, protocol_class)

    await ctx.listen(*address)
    return ctx
