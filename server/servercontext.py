import asyncio

import server
from .decorators import with_logger
from .protocol import QDataStreamProtocol
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
        self.connections = set()
        self._transport = None
        self._logger.debug("%s initialized", self)
        self.addr = None

    def __repr__(self):
        return "ServerContext({})".format(self.name)

    async def listen(self, host, port):
        self.addr = (host, port)
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

    def wait_closed(self):
        return self._server.wait_closed()

    def close(self):
        self._server.close()
        self._logger.debug("%s Closed", self)

    def __contains__(self, connection):
        return connection in self.connections

    def broadcast(self, message, validate_fn=lambda a: True):
        server.stats.incr('server.broadcasts')
        for conn in self.connections:
            if validate_fn(conn):
                conn.protocol.send_message(message)

    def broadcast_raw(self, message: bytes):
        """ Deprecated function used for sending PING messages """
        server.stats.incr('server.broadcasts')
        for conn in self.connections:
            conn.protocol.send_raw(message)

    async def client_connected(self, stream_reader, stream_writer):
        self._logger.debug("%s: Client connected", self)
        protocol = QDataStreamProtocol(stream_reader, stream_writer)
        connection = self._connection_factory(
            protocol=protocol,
            peername=Address(*stream_writer.get_extra_info('peername'))
        )
        try:
            self.connections.add(connection)
            server.stats.gauge('user.agents.None', 1, delta=True)
            while True:
                message = await protocol.read_message()
                with server.stats.timer('connection.on_message_received'):
                    await connection.on_message_received(message)
                with server.stats.timer('servercontext.drain'):
                    await asyncio.sleep(0)
                    await connection.drain()
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
            self.connections.remove(connection)
            server.stats.gauge('user.agents.{}'.format(connection.user_agent), -1, delta=True)
            protocol.writer.close()
            await connection.on_connection_lost()
