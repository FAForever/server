"""
Forged Alliance Forever lobby server.

# Overview
The lobby server handles live state information for the FAF ecosystem. This
includes maintaining a list of online players, a list of hosted and ongoing
games, and a number of matchmakers. It also performs certain post-game actions
like computing and persisting rating changes and updating achievements. Every
online player maintains an active TCP connection to the server through which
the server syncronizes the current state.

## Social
The social components of the lobby server are relatively limited, as the
primary social element, chat, is handled by a separate server. The social
features handled by the lobby server are therefore limited to:

- Syncronizing online player state
- Enforcing global bans
- Modifying a list of friends and a list of foes
- Modifying the currently selected avatar

## Games
The server supports two ways of discovering games with other players: custom
lobbies and matchmakers. Ultimately however, the lobby server is only able to
help players discover eachother, and maintain certain meta information about
games. Game simulation happens entirely on the client side, and is completely
un-controlled by the server. Certain messages sent between clients throughout
the course of a game will also be relayed to the server. These can be used to
determine if clients were able to connect to eachother, and what the outcome of
the game was.

### Custom Games
Historically, the standard way to play FAF has been for one player to host a
game lobby, setup the desired map and game settings, and for other players to
voluntarily join that lobby until the host is satisfied with the players and
launches the game. The lobby server facilitates sending certain information
about these custom lobbies to all online players (subject to friend/foe rules)
as well as managing a game id that can be used to join a specific lobby. This
information includes, but is not necessarily limited to:

- Auto generated game uid
- Host specified game name
- Host selected map
- List of connected players (non-AI only) and their team setup

### Matchmaker games
Players may also choose to join a matchmaker queue, instead of hosting a game
and finding people to play with manually. The matchmaker will attempt to create
balanced games using players TrueSkill rating, and choose a game host for
hosting an automatch lobby. From the server perspective, automatch games behave
virtually identical to custom games, the exception being that players may not
request to join them by game id. The exchange of game messages and connectivity
establishment happens identically to custom games.

### Connectivity Establishment
When a player requests to join a game, the lobby server initiates connection
establishment between the joining player and the host, and then the joining
player and all other players in the match. Connections are then established
using the Interactive Connectivity Establishment (ICE) protocol, using the
lobby server as a medium of exchanging candidate addresses between clients. If
clients require a relay in order to connect to eachother, they will
authenticate with a separate coturn server using credentials supplied by the
lobby server.

## Achievements
When a game ends, each client will report a summary of the game in the form of
a stat report. These stats are then parsed to extract information about events
that occurred during the game, like units built, units killed, etc. and used to
unlock or progress achievements for the players.

# Technical Overview
This section is intended for developers and will outline technical details of
how to interact with the server. It will remain relatively high level and
implementation agnostic, instead linking to other sections of the documentation
that go into more detail.

## Protocol
TODO

# Legal
- Copyright © 2012-2014 Gael Honorez
- Copyright © 2015-2016 Michael Søndergaard <sheeo@faforever.com>
- Copyright © 2021 Forged Alliance Forever

Distributed under GPLv3, see license.txt
"""

import asyncio
import logging
import time
from typing import Optional

import server.metrics as metrics

from .asyncio_extensions import map_suppress, synchronizedmethod
from .broadcast_service import BroadcastService
from .config import TRACE, config
from .configuration_service import ConfigurationService
from .core import Service, create_services
from .db import FAFDatabase
from .game_service import GameService
from .gameconnection import GameConnection
from .geoip_service import GeoIpService
from .ice_servers.nts import TwilioNTS
from .ladder_service import LadderService
from .ladder_service.violation_service import ViolationService
from .lobbyconnection import LobbyConnection
from .message_queue_service import MessageQueueService
from .oauth_service import OAuthService
from .party_service import PartyService
from .player_service import PlayerService
from .protocol import Protocol, QDataStreamProtocol
from .rating_service.rating_service import RatingService
from .servercontext import ServerContext
from .stats.game_stats_service import GameStatsService

__author__ = "Askaholic, Chris Kitching, Dragonfire, Gael Honorez, Jeroen De Dauw, Crotalus, Michael Søndergaard, Michel Jung"
__contact__ = "admin@faforever.com"
__license__ = "GPLv3"
__copyright__ = "Copyright (c) 2011-2015 " + __author__

__all__ = (
    "BroadcastService",
    "ConfigurationService",
    "GameConnection",
    "GameService",
    "GameStatsService",
    "GeoIpService",
    "LadderService",
    "MessageQueueService",
    "OAuthService",
    "PartyService",
    "PlayerService",
    "RatingService",
    "RatingService",
    "ServerInstance",
    "ViolationService",
    "game_service",
    "protocol",
)

logger = logging.getLogger("server")


class ServerInstance(object):
    """
    A class representing a shared server state. Each `ServerInstance` may be
    exposed on multiple ports, but each port will share the same internal server
    state, i.e. the same players, games, etc.
    """

    def __init__(
        self,
        name: str,
        database: FAFDatabase,
        twilio_nts: Optional[TwilioNTS],
        loop: asyncio.BaseEventLoop,
        # For testing
        _override_services: Optional[dict[str, Service]] = None
    ):
        self.name = name
        self._logger = logging.getLogger(self.name)
        self.database = database
        self.twilio_nts = twilio_nts
        self.loop = loop

        self.started = False

        self.contexts: set[ServerContext] = set()

        self.services = _override_services or create_services({
            "server": self,
            "database": self.database,
            "loop": self.loop,
        })

        self.connection_factory = lambda: LobbyConnection(
            database=database,
            geoip=self.services["geo_ip_service"],
            game_service=self.services["game_service"],
            nts_client=twilio_nts,
            players=self.services["player_service"],
            ladder_service=self.services["ladder_service"],
            party_service=self.services["party_service"],
            rating_service=self.services["rating_service"],
            oauth_service=self.services["oauth_service"],
        )

    def write_broadcast(
        self,
        message,
        predicate=lambda conn: conn.authenticated
    ):
        """
        Queue a message to be sent to all connected clients.
        """
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
    async def start_services(self) -> None:
        if self.started:
            return

        num_services = len(self.services)
        self._logger.debug("Initializing %s services", num_services)

        async def initialize(service):
            start = time.perf_counter()
            await service.initialize()
            service._logger.debug(
                "%s initialized in %0.2f seconds",
                service.__class__.__name__,
                time.perf_counter() - start
            )

        await asyncio.gather(*[
            initialize(service) for service in self.services.values()
        ])

        self._logger.debug("Initialized %s services", num_services)

        self.started = True

    async def listen(
        self,
        address: tuple[str, int],
        name: Optional[str] = None,
        protocol_class: type[Protocol] = QDataStreamProtocol,
        proxy: bool = False,
    ) -> ServerContext:
        """
        Start listening on a new address.

        # Params
        - `address`: Tuple indicating the host, port to listen on.
        - `name`: String used to identify this context in log messages. The
            default is to use the `protocol_class` name.
        - `protocol_class`: The protocol class implementation to use.
        - `proxy`: Boolean indicating whether or not to use the PROXY protocol.
            See: https://www.haproxy.org/download/1.8/doc/proxy-protocol.txt
        """
        if not self.started:
            await self.start_services()

        ctx = ServerContext(
            f"{self.name}[{name or protocol_class.__name__}]",
            self.connection_factory,
            list(self.services.values()),
            protocol_class
        )
        await ctx.listen(*address, proxy=proxy)

        self.contexts.add(ctx)

        return ctx

    async def graceful_shutdown(self):
        """
        Start a graceful shut down of the server.

        1. Notify all services of graceful shutdown
        """
        self._logger.info("Initiating graceful shutdown")

        await map_suppress(
            lambda service: service.graceful_shutdown(),
            self.services.values(),
            logger=self._logger,
            msg="when starting graceful shutdown of service "
        )

    async def shutdown(self):
        """
        Immediately shutdown the server.

        1. Stop accepting new connections
        2. Stop all services
        3. Close all existing connections
        """
        self._logger.info("Initiating full shutdown")

        await self._stop_contexts()
        await self._shutdown_services()
        await self._shutdown_contexts()

        self.contexts.clear()
        self.started = False

    async def drain(self):
        """
        Wait for all games to end.
        """
        game_service: GameService = self.services["game_service"]
        broadcast_service: BroadcastService = self.services["broadcast_service"]
        try:
            await asyncio.wait_for(
                game_service.drain_games(),
                timeout=config.SHUTDOWN_GRACE_PERIOD
            )
        except asyncio.CancelledError:
            self._logger.debug(
                "Stopped waiting for games to end due to forced shutdown"
            )
        except asyncio.TimeoutError:
            self._logger.warning(
                "Graceful shutdown period ended! %s games are still live!",
                len(game_service.live_games)
            )
        finally:
            # The report_dirties loop is responsible for clearing dirty games
            # and broadcasting the update messages to players and to RabbitMQ.
            # We need to wait here for that loop to complete otherwise it is
            # possible for the services to be shut down inbetween clearing the
            # games and posting the messages, causing the posts to fail.
            await broadcast_service.wait_report_dirtes()

    async def _shutdown_services(self):
        await map_suppress(
            lambda service: service.shutdown(),
            self.services.values(),
            logger=self._logger,
            msg="when shutting down service "
        )

    async def _stop_contexts(self):
        await map_suppress(
            lambda ctx: ctx.stop(),
            self.contexts,
            logger=self._logger,
            msg="when stopping context "
        )

    async def _shutdown_contexts(self):
        await map_suppress(
            lambda ctx: ctx.shutdown(),
            self.contexts,
            logger=self._logger,
            msg="when shutting down context "
        )
