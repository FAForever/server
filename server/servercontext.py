import asyncio

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
        self._transport = None
        self._logger.info("{} initialized with loop: {}".format(self, loop))
        self.addr = None

    def __repr__(self):
        return "ServerContext({})".format(self.name)

    async def listen(self, host, port):
        self.addr = (host, port)
        self._logger.info("ServerContext.listen({},{})".format(host, port))
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
        self._logger.info("Closed")

    def __contains__(self, connection):
        return connection in self.connections.keys()

    def broadcast_raw(self, message, validate_fn=lambda a: True):
        server.stats.incr('server.broadcasts')
        for conn, proto in self.connections.items():
            if validate_fn(conn):
                proto.send_raw(message)

    async def client_connected(self, stream_reader, stream_writer):
        self._logger.info("{}: Client connected".format(self))
        protocol = QDataStreamProtocol(stream_reader, stream_writer)
        try:
            connection = self._connection_factory()
            await connection.on_connection_made(protocol, Address(*stream_writer.get_extra_info('peername')))
            self.connections[connection] = protocol
        except Exception as ex:
            self._logger.exception(ex)
            return
        try:
            while True:
                message = await protocol.read_message()
                await connection.on_message_received(message)
        except ConnectionResetError:
            pass
        except ConnectionAbortedError:
            pass
        except asyncio.IncompleteReadError as ex:
            if not stream_reader.at_eof():
                self._logger.exception(ex)
        except Exception as ex:
            self._logger.exception(ex)
        finally:
            del self.connections[connection]
            protocol.writer.close()
            await connection.on_connection_lost()
