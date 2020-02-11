import asyncio

import server

from .async_functions import gather_without_exceptions
from .config import TRACE
from .decorators import with_logger
from .protocol import DisconnectedError, QDataStreamProtocol
from .types import Address


@with_logger
class ServerContext:
    """
    Base class for managing connections and holding state about them.
    """

    def __init__(self, connection_factory, name='Unknown server'):
        super().__init__()
        self.name = name
        self._server = None
        self._connection_factory = connection_factory
        self.connections = {}
        self._logger.debug("%s initialized", self)

    def __repr__(self):
        return "ServerContext({})".format(self.name)

    async def listen(self, host, port):
        self._logger.debug("ServerContext.listen(%s, %s)", host, port)
        # TODO: Use tags so we don't need to manually reset each one
        server.stats.gauge('user.agents.None', 0)
        server.stats.gauge('user.agents.downlords_faf_client', 0)
        server.stats.gauge('user.agents.faf_client', 0)

        self._server = await asyncio.start_server(
            self.client_connected,
            host=host,
            port=port
        )
        return self._server

    @property
    def sockets(self):
        return self._server.sockets

    def wait_closed(self):
        return self._server.wait_closed()

    def close(self):
        self._server.close()
        self._logger.debug("%s Closed", self)

    def __contains__(self, connection):
        return connection in self.connections.keys()

    async def broadcast(self, message, validate_fn=lambda a: True):
        await self._do_broadcast(
            validate_fn,
            lambda proto: proto.send_message(message)
        )
        self._logger.log(TRACE, "]]: %s", message)

    async def broadcast_raw(self, message, validate_fn=lambda a: True):
        await self._do_broadcast(
            validate_fn,
            lambda proto: proto.send_raw(message)
        )

    async def _do_broadcast(self, validate_fn, map_fn):
        server.stats.incr('server.broadcasts')
        tasks = []
        for conn, proto in self.connections.items():
            if validate_fn(conn):
                tasks.append(map_fn(proto))

        await gather_without_exceptions(tasks, DisconnectedError)

    async def client_connected(self, stream_reader, stream_writer):
        self._logger.debug("%s: Client connected", self)
        protocol = QDataStreamProtocol(stream_reader, stream_writer)
        connection = self._connection_factory()
        try:
            await connection.on_connection_made(protocol, Address(*stream_writer.get_extra_info('peername')))
            self.connections[connection] = protocol
            server.stats.gauge('user.agents.None', 1, delta=True)
            while protocol.connected:
                message = await protocol.read_message()
                with server.stats.timer('connection.on_message_received'):
                    await connection.on_message_received(message)
        except ConnectionError:
            # User disconnected. Proceed to finally block for cleanup.
            pass
        except TimeoutError:
            pass
        except asyncio.IncompleteReadError as ex:
            if not stream_reader.at_eof():
                self._logger.exception(ex)
        except Exception as ex:
            self._logger.exception(ex)
        finally:
            del self.connections[connection]
            server.stats.gauge('user.agents.{}'.format(connection.user_agent), -1, delta=True)
            protocol.writer.close()
            await connection.on_connection_lost()
