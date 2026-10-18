"""
Manages a group of connections using RabbitMQ as the transport.
"""

import asyncio
import json
import logging
import socket
from contextlib import contextmanager
from typing import Callable, ClassVar, Iterable, Optional

import humanize
from aio_pika.abc import AbstractIncomingMessage, AbstractQueue

import server.metrics as metrics
from .core import Service
from .decorators import with_logger
from .lobbyconnection import LobbyConnection
from .message_queue_service import MessageQueueService
from .protocol import DisconnectedError, RabbitMQProtocol
from .types import Address
from .config import TRACE

@with_logger
class ServerContext:
    """
    Base class for managing connections and holding state about them using RabbitMQ.
    """

    _logger: ClassVar[logging.Logger]

    def __init__(
        self,
        name: str,
        connection_factory: Callable[[], LobbyConnection],
        services: Iterable[Service],
        message_queue_service: MessageQueueService,
    ):
        super().__init__()
        self.name = name
        self._drain_event: Optional[asyncio.Event] = None
        self._connection_factory = connection_factory
        self._services = list(services)
        self.message_queue_service = message_queue_service

        self.connections: dict[LobbyConnection, RabbitMQProtocol] = {}
        self.sessions: dict[int, tuple[LobbyConnection, RabbitMQProtocol]] = {}
        self._consumer_tags: list[tuple[AbstractQueue, str]] = []
        self._tasks: set[asyncio.Task] = set()

        self.connection_exchange: Optional[str] = None
        self.auth_exchange: Optional[str] = None

    def __repr__(self):
        return f"ServerContext({self.name})"

    async def listen(
        self,
        client_exchange: str,
        session_exchange: str,
        session_request_exchange: str,
        client_routing_keys: list[str],
    ):
        self._logger.debug(
            "%s: listen(connection_exchange=%r, auth_exchange=%r)",
            self.name,
            client_exchange,
            session_exchange,
        )

        self.connection_exchange = client_exchange
        self.auth_exchange = session_exchange

        hostname = socket.gethostname()

        # Declare and consume state messages (already authenticated player connected)
        session_queue_name = f"{session_exchange}.state.{hostname}"
        session_consumer = await self.message_queue_service.declare_queue_and_consume(
            exchange_name=session_exchange,
            routing_keys=["#"],
            callback=self._on_session_message,
            queue_name=session_queue_name,
        )
        if session_consumer is not None:
            self._consumer_tags.append(session_consumer)

        # Declare and consume client messages
        client_queue_name = f"{client_exchange}.client.{hostname}"
        client_consumer = await self.message_queue_service.declare_queue_and_consume(
            exchange_name=client_exchange,
            routing_keys=client_routing_keys,
            callback=self._on_client_message,
            queue_name=client_queue_name,
        )
        if client_consumer is not None:
            self._consumer_tags.append(client_consumer)

        await self.message_queue_service.publish(session_request_exchange, "", {}, reply_to=session_queue_name)

        self._logger.info(
            "%s: listening on RabbitMQ exchanges: connection=%s, state=%s",
            self.name,
            client_exchange,
            session_exchange,
        )

    async def _on_session_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                payload = json.loads(message.body)
            except (ValueError, UnicodeDecodeError):
                self._logger.warning("Dropping session message with non-JSON body")
                return

            self._logger.log(TRACE, "Received session message: %s", payload)

            if not isinstance(payload, dict):
                self._logger.warning("Dropping session message: payload is not a JSON object")
                return

            player_id = payload.get("player_id")

            if player_id is None:
                self._logger.warning("Dropping session message: missing player_id")
                return

            try:
                player_id = int(player_id)
            except (TypeError, ValueError):
                self._logger.warning("Dropping session message: invalid player_id %r", player_id)
                return

            session_id = payload.get("session_id")
            if session_id is None:
                self._logger.warning("Dropping session message: missing session_id")
                return

            try:
                session_id = int(session_id)
            except (TypeError, ValueError):
                self._logger.warning("Dropping session message: invalid session_id %r", session_id)
                return

            state = payload.get("state")
            if not isinstance(state, dict):
                self._logger.warning("Dropping session message: missing state")
                return

            state_type = state.get("@type")
            host = payload.get("ip_address") or "unknown"
            if state_type == "new":
                self.create_session(host, player_id, session_id, True)
            elif state_type == "existing":
                if not session_id in self.sessions:
                    self.create_session(host, player_id, session_id, False)

            elif state_type == "gone":
                if session_id is None:
                    self._logger.debug(
                        "%s: Dropping 'gone' session message for player %s: missing session_id",
                        self.name,
                        player_id,
                    )
                    return

                try:
                    session_key = int(session_id)
                except (TypeError, ValueError):
                    self._logger.warning(
                        "%s: Dropping 'gone' session message: invalid session_id %r",
                        self.name,
                        session_id,
                    )
                    return

                conn_tuple = self.sessions.get(session_key)
                if conn_tuple is not None:
                    conn, proto = conn_tuple
                    self._logger.info(
                        "%s: Closing connection for player %s with session %s (gone)",
                        self.name,
                        player_id,
                        conn.session,
                    )
                    await proto.close()
                else:
                    self._logger.debug(
                        "%s: No active connection found to close for session %s (player %s)",
                        self.name,
                        session_id,
                        player_id,
                    )

    def create_session(self, host: str, player_id: int, session_id: int, new_connection: bool):
        peername = Address(host, 0)

        connection = self._connection_factory()
        if session_id is not None:
            try:
                connection.session = int(session_id)
            except (TypeError, ValueError):
                pass

        queue: asyncio.Queue = asyncio.Queue()
        protocol = RabbitMQProtocol(
            queue=queue,
            message_queue_service=self.message_queue_service,
            session=connection.session,
        )

        self.connections[connection] = protocol
        self.sessions[connection.session] = (connection, protocol)

        self._logger.info(
            "%s: Authenticated player %s connected with session %s",
            self.name,
            player_id,
            connection.session,
        )

        task = asyncio.create_task(
            self.handle_client_connected(connection, protocol, peername, player_id, new_connection)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _on_client_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                payload = json.loads(message.body)
            except (ValueError, UnicodeDecodeError):
                self._logger.warning("Dropping connection message with non-JSON body")
                return

            self._logger.log(TRACE, "Received client message: %s", payload)

            if not isinstance(payload, dict):
                self._logger.warning("Dropping connection message: payload is not a JSON object")
                return

            session_id = payload.get("session_id")
            if session_id is None and isinstance(payload.get("target"), dict):
                session_id = payload["target"].get("session_id") or payload["target"].get("session")

            if session_id is None:
                self._logger.warning("Dropping connection message: missing session_id")
                return

            try:
                session_id = int(session_id)
            except (TypeError, ValueError):
                self._logger.warning("Dropping connection message: invalid session_id %r", session_id)
                return

            conn_tuple = self.sessions.get(session_id)
            if conn_tuple is None:
                self._logger.debug("Dropping connection message: session %s not found on this context", session_id)
                return

            conn, proto = conn_tuple
            inner_message = payload.get("message", payload)
            if not isinstance(inner_message, dict):
                inner_message = payload

            await proto.queue.put(inner_message)

    async def shutdown(self, timeout: Optional[float] = 5):
        self._logger.debug("%s: stop serving", self.name)

        # Cancel consumers
        for queue, consumer_tag in self._consumer_tags:
            try:
                await queue.cancel(consumer_tag)
            except Exception:
                pass
        self._consumer_tags.clear()

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

        if timeout is None:
            self._logger.debug(
                "%s: Waiting for connections to close",
                self.name,
            )
        else:
            self._logger.debug(
                "%s: Waiting up to %s for connections to close",
                self.name,
                humanize.naturaldelta(timeout)
            )

        for fut in asyncio.as_completed([
            close_or_abort(conn, proto)
            for conn, proto in list(self.connections.items())
        ]):
            await fut

        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._logger.debug("%s: All connections closed", self.name)

    async def drain_connections(self):
        """
        Wait for all connections to terminate.
        """
        if not self.connections:
            return

        if not self._drain_event:
            self._drain_event = asyncio.Event()

        await self._drain_event.wait()

    def write_broadcast(self, message: dict, validate_fn=lambda _: True):
        for conn, proto in list(self.connections.items()):
            try:
                if proto.is_connected() and validate_fn(conn):
                    proto.write_message(message)
            except Exception:
                self._logger.exception(
                    "%s: Encountered error in broadcast: %s",
                    self.name,
                    conn
                )

    def write_broadcast_raw(self, data: bytes, validate_fn=lambda _: True):
        for conn, proto in list(self.connections.items()):
            try:
                if proto.is_connected() and validate_fn(conn):
                    proto.write_raw(data)
            except Exception:
                self._logger.exception(
                    "%s: Encountered error in broadcast: %s",
                    self.name,
                    conn
                )

    async def handle_client_connected(
        self,
        connection: LobbyConnection,
        protocol: RabbitMQProtocol,
        peername: Address,
        player_id: int,
        new_connection: bool,
    ):
        try:
            await connection.on_connection_made(protocol, peername)
            await connection.on_external_auth(player_id, "broker", new_connection)
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
            self.connections.pop(connection, None)
            self.sessions.pop(connection.session, None)
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
