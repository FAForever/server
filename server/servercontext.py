"""
Manages a group of connections using the same protocol over the same port
"""

import asyncio
import socket
from contextlib import contextmanager
from typing import Callable, Iterable, Optional

import humanize

import server.metrics as metrics

from .core import Service
from .decorators import with_logger
from .lobbyconnection import LobbyConnection
from .protocol import DisconnectedError, Protocol, SimpleJsonProtocol
from .types import Address


@with_logger
class ServerContext:
    """
    Base class for managing connections and holding state about them.
    """

    def __init__(
        self,
        name: str,
        connection_factory: Callable[[], LobbyConnection],
        services: Iterable[Service],
        protocol_class: type[Protocol] = SimpleJsonProtocol,
    ):
        super().__init__()
        self.name = name
        self._server = None
        self._connection_factory = connection_factory
        self._services = services
        self.connections: dict[LobbyConnection, Protocol] = {}
        self.protocol_class = protocol_class

    def __repr__(self):
        return f"ServerContext({self.name})"

    async def listen(self, host, port):
        self._logger.debug("%s: listen(%s, %s)", self.name, host, port)

        self._server = await asyncio.start_server(
            self.client_connected,
            host=host,
            port=port
        )

        for sock in self.sockets:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        return self._server

    @property
    def sockets(self):
        return self._server.sockets

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
        self._logger.debug(
            "%s: Waiting up to %s for connections to close",
            self.name,
            humanize.naturaldelta(timeout)
        )
        for fut in asyncio.as_completed([
            close_or_abort(conn, proto)
            for conn, proto in self.connections.items()
        ]):
            await fut
        self._logger.debug("%s: All connections closed", self.name)

    async def stop(self):
        self._server.close()
        await self._server.wait_closed()
        self._logger.debug("%s: stop()", self.name)

    def __contains__(self, connection):
        return connection in self.connections

    def write_broadcast(self, message, validate_fn=lambda _: True):
        self.write_broadcast_raw(
            self.protocol_class.encode_message(message),
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

    async def client_connected(self, stream_reader, stream_writer):
        self._logger.debug("%s: Client connected", self.name)
        protocol = self.protocol_class(stream_reader, stream_writer)
        connection = self._connection_factory()
        self.connections[connection] = protocol

        try:
            await connection.on_connection_made(
                protocol,
                Address(*stream_writer.get_extra_info("peername"))
            )
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
        except Exception:
            self._logger.exception()
        finally:
            del self.connections[connection]
            # Do not wait for buffers to empty here. This could stop the process
            # from exiting if the client isn't reading data.
            protocol.abort()
            with self.suppress_and_log(connection.on_connection_lost, Exception):
                await connection.on_connection_lost()

            for service in self._services:
                with self.suppress_and_log(service.on_connection_lost, Exception):
                    service.on_connection_lost(connection)

            self._logger.debug("%s: Client disconnected", self.name)
            metrics.user_connections.labels(
                connection.user_agent,
                connection.version
            ).dec()

    @contextmanager
    def suppress_and_log(self, func, *exceptions: type[BaseException]):
        try:
            yield
        except exceptions:
            if hasattr(func.__self__):
                desc = f"{func.__self__.__class__}.{func.__name__}"
            else:
                desc = func.__name__
            self._logger.warning(
                "Unexpected exception in %s",
                desc,
                exc_info=True
            )
