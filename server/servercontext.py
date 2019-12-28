import asyncio
from asyncio.locks import Condition

import server
from server.decorators import with_logger
from server.protocol import QDataStreamProtocol
from server.types import Address


@with_logger
class ServerContext:
    """
    Base class for managing connections and holding state about them.
    """

    def __init__(self, connection_factory, throttler, name='Unknown server'):
        super().__init__()
        self.name = name
        self._server = None
        self._throttler = throttler
        self._connection_factory = connection_factory
        self.connections = {}
        self._logger.debug("%s initialized", self)

    def __repr__(self):
        return "ServerContext({})".format(self.name)

    async def listen(self, host, port):
        self._logger.debug("ServerContext.listen(%s, %s)", host, port)
        self._server = await asyncio.start_server(
            self.client_connected,
            host=host,
            port=port
        )
        return self._server

    @property
    def sockets(self):
        return self._server.sockets

    async def wait_closed(self):
        if self._throttler is not None:
            await self._throttler.close()
        return await self._server.wait_closed()

    def close(self):
        self._server.close()
        self._logger.debug("%s Closed", self)

    def __contains__(self, connection):
        return connection in self.connections.keys()

    async def broadcast_raw(self, message, validate_fn=lambda a: True):
        server.stats.incr('server.broadcasts')
        tasks = []
        for conn, proto in self.connections.items():
            if validate_fn(conn):
                tasks.append(proto.send_raw(message))

        await asyncio.gather(*tasks)

    async def client_connected(self, stream_reader, stream_writer):
        self._logger.debug("%s: Client connected", self)
        if self._throttler is not None:
            await self._throttler.consume()
        protocol = QDataStreamProtocol(stream_reader, stream_writer)
        connection = self._connection_factory()
        try:
            await connection.on_connection_made(protocol, Address(*stream_writer.get_extra_info('peername')))
            self.connections[connection] = protocol
            server.stats.gauge('user.agents.None', 1, delta=True)
            while True:
                message = await protocol.read_message()
                with server.stats.timer('connection.on_message_received'):
                    await connection.on_message_received(message)
        except ConnectionResetError:
            pass
        except ConnectionAbortedError:
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
