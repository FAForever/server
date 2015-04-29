import asyncio
from server.decorators import with_logger
from server.protocol import QDataStreamProtocol


@with_logger
class ServerContext():
    """
    Base class for managing connections and holding state about them.
    """

    def __init__(self, connection_factory, loop=asyncio.get_event_loop()):
        super().__init__()
        self.loop = loop
        self._server = None
        self._connection_factory = connection_factory
        self.connections = []
        self._transport = None
        self._logger.info("ServerContext initialized")

    def listen(self, host, port):
        self._logger.info("ServerContext.listen({},{})".format(host, port))
        self._server = asyncio.start_server(self.client_connected,
                                            host=host,
                                            port=port,
                                            loop=self.loop)
        return self._server

    def close(self):
        self._server.close()

    def __contains__(self, connection):
        return connection in self.connections

    @asyncio.coroutine
    def client_connected(self, stream_reader, stream_writer):
        self._logger.info("Client connected")
        protocol = QDataStreamProtocol(stream_reader, stream_writer)
        connection = self._connection_factory(protocol)
        connection.on_connection_made(protocol, stream_writer.get_extra_info('peername'))
        self.connections.append(connection)
        try:
            while True:
                message = yield from protocol.read_message()
                connection.on_message_received(message)
        except asyncio.IncompleteReadError as ex:
            if not stream_reader.at_eof():
                self._logger.exception(ex)
                raise
        except Exception as ex:
            self._logger.exception(ex)
        finally:
            self.connections.remove(connection)
            connection.on_connection_lost()
