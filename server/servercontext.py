"""
Manages a group of connections using the same protocol over the same port
"""

import asyncio
import socket
from typing import Callable, Dict, Iterable, Type

import server.metrics as metrics

from .core import Service
from .decorators import with_logger
from .lobbyconnection import LobbyConnection
from .protocol import DisconnectedError, Protocol, QDataStreamProtocol
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
        protocol_class: Type[Protocol] = QDataStreamProtocol,
    ):
        super().__init__()
        self.name = name
        self._server = None
        self._connection_factory = connection_factory
        self._services = services
        self.connections: Dict[LobbyConnection, Protocol] = {}
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

    def wait_closed(self):
        return self._server.wait_closed()

    def close(self):
        self._server.close()
        self._logger.debug("%s closed", self.name)

    def __contains__(self, connection):
        return connection in self.connections.keys()

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
                    "Encountered error in broadcast: %s", conn
                )

    async def client_connected(self, stream_reader, stream_writer):
        self._logger.debug("%s: Client connected", self.name)
        protocol = self.protocol_class(stream_reader, stream_writer)
        connection = self._connection_factory()
        self.connections[connection] = protocol

        try:
            await connection.on_connection_made(protocol, Address(*stream_writer.get_extra_info("peername")))
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
        except Exception as ex:
            self._logger.exception(ex)
        finally:
            del self.connections[connection]
            await protocol.close()
            await connection.on_connection_lost()

            for service in self._services:
                try:
                    service.on_connection_lost(connection)
                except Exception:
                    self._logger.warning(
                        "Unexpected exception in %s.on_connection_lost",
                        service.__class__.__name__,
                        exc_info=True
                    )

            self._logger.debug("%s: Client disconnected", self.name)
            metrics.user_connections.labels(
                connection.user_agent,
                connection.version
            ).dec()
