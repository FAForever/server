import asyncio
from collections import defaultdict

import server
from server.decorators import with_logger
from server.protocol import QDataStreamProtocol
from server.types import Address


@with_logger
class ServerContext:
    """
    Base class for managing connections and holding state about them.
    """

    def __init__(self, connection_factory, loop, name='Unknown server'):
        super().__init__()
        self.loop = loop
        self.name = name
        self._server = None
        self._connection_factory = connection_factory
        self.connections = {}
        self.connection_by_user_agent = defaultdict(dict)
        self._transport = None
        self._logger.debug("%s initialized with loop: %s", self, loop)
        self.addr = None

    def __repr__(self):
        return "ServerContext({})".format(self.name)

    async def listen(self, host, port):
        self.addr = (host, port)
        self._logger.debug("ServerContext.listen(%s,%d)", host, port)
        self._server = await asyncio.start_server(self.client_connected,
                                            host=host,
                                            port=port,
                                            loop=self.loop)
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

    def broadcast_raw(self, message, validate_fn=lambda a: True):
        server.stats.incr('server.broadcasts')
        for conn, proto in self.connections.items():
            if validate_fn(conn):
                proto.send_raw(message)

    def assign_connection_by_user_agent(self, connection, protocol):
        if connection.user_agent:
            collection = self.connection_by_user_agent[connection.user_agent]
            if connection not in collection:
                del self.connection_by_user_agent[None][connection]
                collection[connection] = protocol

    def remove_connection_by_user_agent(self, connection):
        if connection.user_agent in self.connection_by_user_agent:
            collection = self.connection_by_user_agent[connection.user_agent]
        else:
            collection = self.connection_by_user_agent[None]
        collection.pop(connection)

    async def client_connected(self, stream_reader, stream_writer):
        self._logger.debug("%s: Client connected", self)
        protocol = QDataStreamProtocol(stream_reader, stream_writer)
        connection = self._connection_factory()
        try:
            await connection.on_connection_made(protocol, Address(*stream_writer.get_extra_info('peername')))
            self.connections[connection] = protocol
            self.connection_by_user_agent[None][connection] = protocol  # We still want to probably track no user_agent
            while True:
                message = await protocol.read_message()
                with server.stats.timer('connection.on_message_received'):
                    await connection.on_message_received(message)
                    self.assign_connection_by_user_agent(connection, protocol)
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
            del self.connections[connection]
            self.remove_connection_by_user_agent(connection)
            protocol.writer.close()
            await connection.on_connection_lost()
