"""
Manages a group of connections using WebSocket as the transport.
"""

import asyncio
import logging
from contextlib import contextmanager
from typing import Callable, ClassVar, Iterable, Optional

import humanize
from aiohttp import web

import server.metrics as metrics

from .config import config
from .core import Service
from .decorators import with_logger
from .lobbyconnection import LobbyConnection
from .protocol import DisconnectedError, WebSocketProtocol
from .types import Address


@with_logger
class ServerContext:
    """
    Base class for managing connections and holding state about them.
    """

    _logger: ClassVar[logging.Logger]

    def __init__(
        self,
        name: str,
        connection_factory: Callable[[], LobbyConnection],
        services: Iterable[Service],
    ):
        super().__init__()
        self.name = name
        self._drain_event: Optional[asyncio.Event] = None
        self._connection_factory = connection_factory
        self._services = services
        self.connections: dict[LobbyConnection, WebSocketProtocol] = {}

        self.app = web.Application()
        self.runner = web.AppRunner(self.app, access_log=None)
        self.site: Optional[web.TCPSite] = None
        self.host: Optional[str] = None
        self.port: Optional[int] = None
        self.path: str = "/ws"

    def __repr__(self):
        return f"ServerContext({self.name})"

    async def listen(
        self,
        host: str,
        port: Optional[int],
        path: str = "/ws",
    ):
        self._logger.debug(
            "%s: listen(%r, %r, path=%r)",
            self.name,
            host,
            port,
            path,
        )

        self.host = host
        self.port = port
        self.path = path

        self.app.router.add_get(path, self._ws_handler)

        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()

        bound = self.runner.addresses[0]
        self.host, self.port = bound[0], bound[1]

        self._logger.info(
            "%s: listening on ws://%s:%s%s",
            self.name,
            self.host,
            self.port,
            path,
        )

    async def shutdown(self, timeout: Optional[float] = 5):
        async def close_or_abort(conn, proto):
            try:
                await asyncio.wait_for(proto.close(), timeout)
            except asyncio.TimeoutError:
                proto.abort()
                self._logger.warning(
                    "%s: Protocol did not terminate cleanly for '%s'",
                    self.name,
                    conn.get_user_identifier()
                )

        if timeout is None:
            self._logger.debug(
                "%s: Waiting for connections to close",
                self.name,
            )
        else:
            self._logger.debug(
                "%s: Waiting up to %s for connections to close",
                self.name,
                humanize.naturaldelta(timeout)
            )

        self._logger.debug("%s: stop serving", self.name)

        for fut in asyncio.as_completed([
            close_or_abort(conn, proto)
            for conn, proto in self.connections.items()
        ]):
            await fut
        self._logger.debug("%s: All connections closed", self.name)

        await self.runner.cleanup()

    async def drain_connections(self):
        """
        Wait for all connections to terminate.
        """
        if not self.connections:
            return

        if not self._drain_event:
            self._drain_event = asyncio.Event()

        await self._drain_event.wait()

    def write_broadcast(self, message, validate_fn=lambda _: True):
        self.write_broadcast_raw(
            WebSocketProtocol.encode_message(message),
            validate_fn
        )

    def write_broadcast_raw(self, data, validate_fn=lambda _: True):
        for conn, proto in self.connections.items():
            try:
                if proto.is_connected() and validate_fn(conn):
                    proto.write_raw(data)
            except Exception:
                self._logger.exception(
                    "%s: Encountered error in broadcast: %s",
                    self.name,
                    conn
                )

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Only honor a forwarded-IP header when explicitly configured —
        # otherwise clients connecting directly could spoof their peername.
        peer_host = None
        header_name = config.WS_FORWARDED_IP_HEADER
        if header_name:
            forwarded = request.headers.get(header_name, "")
            peer_host = forwarded.split(",")[0].strip() or None

        if not peer_host:
            peer_host = request.remote or "unknown"

        peername = Address(peer_host, 0)

        self._logger.info(
            "%s: Client connected from %s",
            self.name,
            peer_host,
        )

        await self.handle_client_connected(ws, peername)
        return ws

    async def handle_client_connected(
        self,
        ws: web.WebSocketResponse,
        peername: Address,
    ):
        protocol = WebSocketProtocol(ws)
        connection = self._connection_factory()
        self.connections[connection] = protocol

        try:
            await connection.on_connection_made(protocol, peername)
            metrics.user_connections.labels("None", "None").inc()
            while protocol.is_connected():
                message = await protocol.read_message()
                with metrics.connection_on_message_received.time():
                    await connection.on_message_received(message)
        except (
            ConnectionError,
            DisconnectedError,
            TimeoutError,
            asyncio.CancelledError,
        ):
            pass
        except UnicodeDecodeError as e:
            self._logger.exception(
                "%s: Unicode error in protocol for '%s': %s '...%s...'",
                self.name,
                connection.get_user_identifier(),
                e,
                e.object[e.start-20:e.end+20]
            )
        except Exception as e:
            self._logger.exception(
                "%s: Exception in protocol for '%s': %s",
                self.name,
                connection.get_user_identifier(),
                e
            )
        finally:
            del self.connections[connection]
            # Do not wait for buffers to empty here. This could stop the process
            # from exiting if the client isn't reading data.
            protocol.abort()
            for service in self._services:
                with self.suppress_and_log(service.on_connection_lost, Exception):
                    service.on_connection_lost(connection)

            with self.suppress_and_log(connection.on_connection_lost, Exception):
                await connection.on_connection_lost()

            self._logger.info(
                "%s: Client disconnected for '%s'",
                self.name,
                connection.get_user_identifier()
            )

            if (
                self._drain_event is not None
                and not self._drain_event.is_set()
                and not self.connections
            ):
                self._drain_event.set()

            metrics.user_connections.labels(
                connection.user_agent,
                connection.version
            ).dec()

    @contextmanager
    def suppress_and_log(self, func, *exceptions: type[BaseException]):
        try:
            yield
        except exceptions:
            if hasattr(func, "__self__"):
                desc = f"{func.__self__.__class__.__name__}.{func.__name__}"
            else:
                desc = func.__name__
            self._logger.warning(
                "Unexpected exception in %s",
                desc,
                exc_info=True
            )
