import asyncio
from server.decorators import with_logger
from server.protocol import QDataStreamProtocol


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

    def __repr__(self):
        return "ServerContext({})".format(self.name)

    @asyncio.coroutine
    def listen(self, host, port):
        self._logger.info("ServerContext.listen({},{})".format(host, port))
        self._server = yield from asyncio.start_server(self.client_connected,
                                            host=host,
                                            port=port,
                                            loop=self.loop)
        self._logger.info("Closed")
        return self._server

    def close(self):
        self._server.close()
        self._logger.info("Closed")
        del self._server

    def __contains__(self, connection):
        return connection in self.connections.keys()

    def broadcast_raw(self, message, validate_fn=lambda a: True):
        for conn, proto in self.connections.items():
            if validate_fn(conn):
                proto.send_raw(message)

    @asyncio.coroutine
    def client_connected(self, stream_reader, stream_writer):
        self._logger.info("{}: Client connected".format(self))
        protocol = QDataStreamProtocol(stream_reader, stream_writer)
        try:
            connection = self._connection_factory()
            yield from connection.on_connection_made(protocol, stream_writer.get_extra_info('peername'))
            self.connections[connection] = protocol
        except Exception as ex:
            self._logger.exception(ex)
            return
        try:
            while True:
                message = yield from protocol.read_message()
                yield from connection.on_message_received(message)
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
            connection.on_connection_lost()
