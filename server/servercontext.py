"""
Manages a group of connections using the same protocol over the same port
"""

import asyncio
import socket
from asyncio import StreamReader, StreamWriter
from contextlib import contextmanager
from typing import Callable, Iterable, Optional

import humanize
from proxyprotocol.detect import ProxyProtocolDetect
from proxyprotocol.reader import ProxyProtocolReader
from proxyprotocol.sock import SocketInfo

import server.metrics as metrics

from .core import Service
from .decorators import with_logger
from .lobbyconnection import LobbyConnection
from .protocol import DisconnectedError, Protocol, QDataStreamProtocol
from .types import Address

MiB = 2 ** 20
LIMIT = 10 * MiB


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
        protocol_class: type[Protocol] = QDataStreamProtocol,
    ):
        super().__init__()
        self.name = name
        self._server = None
        self._drain_event = None
        self._connection_factory = connection_factory
        self._services = services
        self.connections: dict[LobbyConnection, Protocol] = {}
        self.protocol_class = protocol_class

    def __repr__(self):
        return f"ServerContext({self.name})"

    async def listen(
        self,
        host: str,
        port: Optional[int],
        proxy: bool = False
    ):
        self._logger.debug(
            "%s: listen(%r, %r, proxy=%r)",
            self.name,
            host,
            port,
            proxy
        )

        callback = self.client_connected_callback
        if proxy:
            pp_detect = ProxyProtocolDetect()
            pp_reader = ProxyProtocolReader(pp_detect)
            callback = pp_reader.get_callback(callback)

        self._server = await asyncio.start_server(
            callback,
            host=host,
            port=port,
            limit=LIMIT,
        )

        for sock in self.sockets:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            host, port, *_ = sock.getsockname()
            self._logger.info("%s: listening on %s:%s", self.name, host, port)

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
        self._logger.debug("%s: stop()", self.name)
        if self._server:
            self._server.close()
            await self._server.wait_closed()

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

    async def client_connected_callback(
        self,
        reader: StreamReader,
        writer: StreamWriter,
        proxy_info: Optional[SocketInfo] = None,
    ):
        if proxy_info:
            peername_writer = Address(*writer.get_extra_info("peername"))

            if not proxy_info.peername:
                # See security considerations:
                # https://www.haproxy.org/download/1.8/doc/proxy-protocol.txt
                self._logger.warning(
                    "%s: Client connected from %s:%s to a context in proxy "
                    "mode! The connection will be ignored, however this may "
                    "indicate a misconfiguration in your firewall.",
                    self.name,
                    peername_writer.host,
                    peername_writer.port
                )
                writer.close()
                return

            peername = Address(*proxy_info.peername)
            self._logger.info(
                "%s: Client connected from %s:%s via proxy %s:%s",
                self.name,
                peername.host,
                peername.port,
                peername_writer.host,
                peername_writer.port
            )
        else:
            peername = Address(*writer.get_extra_info("peername"))
            self._logger.info(
                "%s: Client connected from %s:%s",
                self.name,
                peername.host,
                peername.port
            )

        await self.handle_client_connected(reader, writer, peername)

    async def handle_client_connected(
        self,
        reader: StreamReader,
        writer: StreamWriter,
        peername: Address,
    ):
        protocol = self.protocol_class(reader, writer)
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
