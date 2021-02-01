import asyncio
import socket
from typing import Callable, Dict, Type

import server.metrics as metrics

from .decorators import with_logger
from .lobbyconnection import LobbyConnection
from .protocol import Protocol, QDataStreamProtocol
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
        protocol_class: Type[Protocol] = QDataStreamProtocol,
    ):
        super().__init__()
        self.name = name
        self._server = None
        self._connection_factory = connection_factory
        self.connections: Dict[LobbyConnection, Protocol] = {}
        self.protocol_class = protocol_class

    def __repr__(self):
        return "ServerContext({})".format(self.name)

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
        except (ConnectionError, TimeoutError, asyncio.CancelledError):
            pass
        except asyncio.IncompleteReadError as ex:
            if not stream_reader.at_eof():
                self._logger.exception(ex)
        except Exception as ex:
            self._logger.exception(ex)
        finally:
            del self.connections[connection]
            metrics.user_connections.labels(connection.user_agent, connection.version).dec()
            await protocol.close()
            await connection.on_connection_lost()
            self._logger.debug("%s: Client disconnected", self.name)
