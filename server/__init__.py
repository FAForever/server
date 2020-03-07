"""
Forged Alliance Forever server project

Copyright (c) 2012-2014 Gael Honorez
Copyright (c) 2015-2016 Michael Søndergaard <sheeo@faforever.com>

Distributed under GPLv3, see license.txt
"""
import asyncio
import logging
from typing import Dict, Optional, Set, Tuple, Type

from prometheus_client import start_http_server

import server.metrics as metrics

from .api.api_accessor import ApiAccessor
from .asyncio_extensions import synchronizedmethod
from .config import TRACE, config
from .configuration_service import ConfigurationService
from .control import run_control_server
from .core import Service, create_services
from .db import FAFDatabase
from .game_service import GameService
from .gameconnection import GameConnection
from .games import GameState
from .geoip_service import GeoIpService
from .ice_servers.nts import TwilioNTS
from .ladder_service import LadderService
from .lobbyconnection import LobbyConnection
from .message_queue_service import MessageQueueService
from .party_service import PartyService
from .player_service import PlayerService
from .protocol import Protocol, QDataStreamProtocol
from .rating_service.rating_service import RatingService
from .servercontext import ServerContext
from .stats.game_stats_service import GameStatsService
from .timing import at_interval

__author__ = "Askaholic, Chris Kitching, Dragonfire, Gael Honorez, Jeroen De Dauw, Crotalus, Michael Søndergaard, Michel Jung"
__contact__ = "admin@faforever.com"
__license__ = "GPLv3"
__copyright__ = "Copyright (c) 2011-2015 " + __author__

__all__ = (
    "ConfigurationService",
    "GameConnection",
    "GameService",
    "GameStatsService",
    "GeoIpService",
    "LadderService",
    "MessageQueueService",
    "PartyService",
    "RatingService",
    "RatingService",
    "ServerInstance",
    "abc",
    "control",
    "game_service",
    "protocol",
    "run_control_server",
)

DIRTY_REPORT_INTERVAL = 1  # Seconds
logger = logging.getLogger("server")

if config.ENABLE_METRICS:
    logger.info("Using prometheus on port: %i", config.METRICS_PORT)
    start_http_server(config.METRICS_PORT)


class ServerInstance(object):
    """
        A class representing a shared server state. Each ServerInstance may be
    exposed on multiple ports, but each port will share the same internal server
    state, i.e. the same players, games, etc.
    """

    def __init__(
        self,
        name: str,
        database: FAFDatabase,
        api_accessor: Optional[ApiAccessor],
        twilio_nts: Optional[TwilioNTS],
        loop: asyncio.BaseEventLoop,
        # For testing
        _override_services: Optional[Dict[str, Service]] = None
    ):
        self.name = name
        self._logger = logging.getLogger(self.name)
        self.database = database
        self.api_accessor = api_accessor
        self.twilio_nts = twilio_nts
        self.loop = loop

        self.started = False

        self.contexts: Set[ServerContext] = set()

        self.services = _override_services or create_services({
            "database": self.database,
            "api_accessor": self.api_accessor,
            "loop": self.loop,
        })

        self.connection_factory = lambda: LobbyConnection(
            database=database,
            geoip=self.services["geo_ip_service"],
            game_service=self.services["game_service"],
            nts_client=twilio_nts,
            players=self.services["player_service"],
            ladder_service=self.services["ladder_service"],
            party_service=self.services["party_service"]
        )

    def write_broadcast(self, message, predicate=lambda conn: conn.authenticated):
        self._logger.log(TRACE, "]]: %s", message)
        metrics.server_broadcasts.inc()

        for ctx in self.contexts:
            try:
                ctx.write_broadcast(message, predicate)
            except Exception:
                self._logger.exception(
                    "Error writing '%s'",
                    message.get("command", message)
                )

    @synchronizedmethod
    async def _start_services(self) -> None:
        if self.started:
            return

        await asyncio.gather(*[
            service.initialize() for service in self.services.values()
        ])

        game_service: GameService = self.services["game_service"]
        player_service: PlayerService = self.services["player_service"]

        @at_interval(DIRTY_REPORT_INTERVAL, loop=self.loop)
        def do_report_dirties():
            game_service.update_active_game_metrics()
            dirty_games = game_service.dirty_games
            dirty_queues = game_service.dirty_queues
            dirty_players = player_service.dirty_players
            game_service.clear_dirty()
            player_service.clear_dirty()

            if dirty_queues:
                self.write_broadcast({
                        "command": "matchmaker_info",
                        "queues": [queue.to_dict() for queue in dirty_queues]
                    }
                )

            if dirty_players:
                self.write_broadcast({
                        "command": "player_info",
                        "players": [player.to_dict() for player in dirty_players]
                    },
                    lambda lobby_conn: lobby_conn.authenticated
                )

            # TODO: This spams squillions of messages: we should implement per-
            # connection message aggregation at the next abstraction layer down :P
            for game in dirty_games:
                if game.state == GameState.ENDED:
                    game_service.remove_game(game)

                # So we're going to be broadcasting this to _somebody_...
                message = game.to_dict()

                self.write_broadcast(
                    message,
                    lambda conn: (
                        conn.authenticated
                        and game.is_visible_to_player(conn.player)
                    )
                )

        @at_interval(45, loop=self.loop)
        def ping_broadcast():
            self.write_broadcast({"command": "ping"})

        self.started = True

    async def listen(
        self,
        address: Tuple[str, int],
        protocol_class: Type[Protocol] = QDataStreamProtocol
    ) -> ServerContext:
        """
        Start listening on a new address.
        """
        if not self.started:
            await self._start_services()

        ctx = ServerContext(
            f"{self.name}[{protocol_class.__name__}]",
            self.connection_factory,
            protocol_class
        )
        self.contexts.add(ctx)

        await ctx.listen(*address)

        return ctx

    async def shutdown(self):
        for ctx in self.contexts:
            ctx.close()

        for ctx in self.contexts:
            try:
                await ctx.wait_closed()
            except Exception:
                self._logger.error(
                    "Encountered unexpected error when trying to shut down "
                    "context %s",
                    ctx
                )

        await asyncio.gather(*[
            service.shutdown() for service in self.services.values()
        ])

        self.started = False
