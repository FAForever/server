"""
Manages a group of connections using RabbitMQ as the transport.
"""

import asyncio
import json
import logging
import socket
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Awaitable, Callable, ClassVar, Iterable, Optional

import aio_pika
import humanize
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    DeliveryMode,
    ExchangeType
)
from aiormq import ProbableAuthenticationError

import server.metrics as metrics
from .config import TRACE, config
from .core import Service
from .decorators import with_logger
from .lobbyconnection import LobbyConnection
from .protocol import DisconnectedError, RabbitMQProtocol
from .timing import LazyIntervalTimer, datetime_now
from .types import Address


class ConnectionAttemptFailed(ConnectionError):
    pass


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
    ):
        super().__init__()
        self.name = name
        self._drain_event: Optional[asyncio.Event] = None
        self._connection_factory = connection_factory
        self._services = list(services)
        self._connection: Optional[AbstractConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._exchanges: dict[str, AbstractExchange] = {}
        self._exchange_types: dict[str, ExchangeType] = {}

        self.connections: dict[LobbyConnection, RabbitMQProtocol] = {}
        self.sessions: dict[int, tuple[LobbyConnection, RabbitMQProtocol]] = {}
        self.sessions_expiration: dict[int, datetime] = {}
        self._consumer_tags: list[tuple[AbstractQueue, str]] = []
        self._tasks: set[asyncio.Task] = set()
        self._session_cleanup_timer: Optional[LazyIntervalTimer] = None

        self.connection_exchange: Optional[str] = None
        self.auth_exchange: Optional[str] = None

    def __repr__(self):
        return f"ServerContext({self.name})"

    async def listen(
        self,
        client_routing_keys: list[str],
    ):
        self._logger.debug(
            "%s: listen",
            self.name,
        )

        await self._connect()
        await self._declare_exchange(config.INBOUND_EXCHANGE_NAME, ExchangeType.TOPIC)
        await self._declare_exchange(config.SESSION_EXCHANGE_NAME, ExchangeType.TOPIC)
        await self._declare_exchange(config.OUTBOUND_EXCHANGE_NAME, ExchangeType.TOPIC)
        await self._declare_exchange(config.SESSION_REQUEST_EXCHANGE_NAME, ExchangeType.TOPIC)

        hostname = socket.gethostname()

        # Declare and consume state messages (already authenticated player connected)
        session_queue_name = f"{config.SESSION_EXCHANGE_NAME}.state.{hostname}"
        session_consumer = await self.declare_queue_and_consume(
            exchange_name=config.SESSION_EXCHANGE_NAME,
            routing_keys=["#"],
            callback=self._on_session_message,
            queue_name=session_queue_name,
        )
        if session_consumer is not None:
            self._consumer_tags.append(session_consumer)

        # Declare and consume client messages
        client_queue_name = f"{config.INBOUND_EXCHANGE_NAME}.client.{hostname}"
        client_consumer = await self.declare_queue_and_consume(
            exchange_name=config.INBOUND_EXCHANGE_NAME,
            routing_keys=client_routing_keys,
            callback=self._on_client_message,
            queue_name=client_queue_name,
        )
        if client_consumer is not None:
            self._consumer_tags.append(client_consumer)

        await self.publish(config.SESSION_REQUEST_EXCHANGE_NAME, "", {}, reply_to=session_queue_name)

        self._logger.info(
            "%s: listening on RabbitMQ exchanges: connection=%s, state=%s",
            self.name,
            config.INBOUND_EXCHANGE_NAME,
            config.SESSION_EXCHANGE_NAME,
        )

        self._session_cleanup_timer = LazyIntervalTimer(
            lambda: config.SESSION_CHECK_INTERVAL,
            self._cleanup_sessions,
            start=True
        )

    async def _connect(self) -> None:
        try:
            self._connection = await aio_pika.connect_robust(
                "amqp://{user}:{password}@{server}:{port}/{vhost}".format(
                    user=config.MQ_USER,
                    password=config.MQ_PASSWORD,
                    vhost=config.MQ_VHOST,
                    server=config.MQ_SERVER,
                    port=config.MQ_PORT,
                ),
                loop=asyncio.get_running_loop(),
            )
        except ProbableAuthenticationError as e:
            self._logger.warning(
                "Unable to connect to RabbitMQ. Incorrect credentials?", exc_info=True
            )
            raise ConnectionAttemptFailed from e
        except ConnectionError as e:
            self._logger.warning(
                "Unable to connect to RabbitMQ. Is it running?", exc_info=True
            )
            raise ConnectionAttemptFailed from e
        except Exception as e:
            self._logger.warning(
                "Unable to connect to RabbitMQ due to unhandled excpetion %s. Incorrect vhost?",
                e,
                exc_info=True,
            )
            raise ConnectionAttemptFailed from e

        assert self._connection is not None

        self._channel = await self._connection.channel(publisher_confirms=True)
        self._logger.debug("Connected to RabbitMQ %r", self._connection)

    async def declare_exchange(
        self, exchange_name: str, exchange_type: ExchangeType = ExchangeType.TOPIC, durable: bool = True
    ) -> None:
        await self._declare_exchange(exchange_name, exchange_type, durable)

    async def _declare_exchange(
        self, exchange_name: str, exchange_type: ExchangeType, durable: bool = True
    ) -> None:
        assert self._channel is not None

        new_exchange = await self._channel.declare_exchange(
            exchange_name,
            exchange_type,
            durable=durable,
        )

        self._exchanges[exchange_name] = new_exchange
        self._exchange_types[exchange_name] = exchange_type

    async def publish(
        self,
        exchange_name: str,
        routing: str,
        payload: dict,
        mandatory: bool = False,
        delivery_mode: DeliveryMode = DeliveryMode.PERSISTENT,
        reply_to: Optional[str] = None,
    ) -> None:
        await self.publish_many(
            exchange_name,
            routing,
            [payload],
            mandatory=mandatory,
            delivery_mode=delivery_mode,
            reply_to=reply_to,
        )

    async def publish_many(
        self,
        exchange_name: str,
        routing: str,
        payloads: Iterable[dict],
        mandatory: bool = False,
        delivery_mode: DeliveryMode = DeliveryMode.PERSISTENT,
        reply_to: Optional[str] = None,
    ) -> None:
        assert self._channel is not None

        exchange = self._exchanges.get(exchange_name)
        if exchange is None:
            raise KeyError(f"Unknown exchange {exchange_name}.")

        for payload in payloads:
            message = aio_pika.Message(
                json.dumps(payload).encode(),
                delivery_mode=delivery_mode,
                content_type="application/json",
                reply_to=reply_to
            )
            await exchange.publish(
                message,
                routing_key=routing,
                mandatory=mandatory
            )
            self._logger.log(
                TRACE,
                "Published message %s to %s/%s",
                payload,
                exchange_name,
                routing
            )

    async def declare_queue_and_consume(
        self,
        exchange_name: str,
        routing_keys: list[str],
        callback: Callable[[AbstractIncomingMessage], Awaitable[None]],
        queue_name: str = "",
        exclusive: bool = True,
        auto_delete: bool = True,
        durable: bool = False,
    ) -> Optional[tuple[AbstractQueue, str]]:
        """
        Declare a queue, bind it to an exchange with the given routing key, and
        start consuming. Returns `(queue, consumer_tag)` so the caller can
        cancel on shutdown.
        """

        assert self._channel is not None

        exchange = self._exchanges.get(exchange_name)
        if exchange is None:
            raise KeyError(f"Unknown exchange {exchange_name}.")

        queue = await self._channel.declare_queue(
            queue_name,
            exclusive=exclusive,
            auto_delete=auto_delete,
            durable=durable,
        )
        for routing_key in routing_keys:
            await queue.bind(exchange, routing_key=routing_key)
        consumer_tag = await queue.consume(callback)

        self._logger.debug(
            "Consuming from queue %r bound to %s/%s",
            queue.name, exchange_name, routing_keys,
        )
        return queue, consumer_tag

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
            ip_address = payload.get("ip_address") or "unknown"
            if state_type == "new":
                self.sessions_expiration[session_id] = datetime_now() + timedelta(seconds=int(state.get("seconds_to_expiry", config.DEFAULT_SESSION_EXPIRATION)))
                if session_id not in self.sessions:
                    self._create_session(ip_address, player_id, session_id, config.PUBLISH_WELCOME_MESSAGE)

            elif state_type == "existing":
                self.sessions_expiration[session_id] = datetime_now() + timedelta(seconds=int(state.get("seconds_to_expiry", config.DEFAULT_SESSION_EXPIRATION)))
                if session_id not in self.sessions:
                    self._create_session(ip_address, player_id, session_id, False)

            elif state_type == "gone":
                await self._remove_session(session_id)

    async def _remove_session(self, session_id: int):

        try:
            session_key = int(session_id)
        except (TypeError, ValueError):
            self._logger.warning(
                "%s: Dropping 'gone' session message: invalid session_id %r",
                self.name,
                session_id,
            )
            return

        self.sessions_expiration.pop(session_key, None)
        conn_tuple = self.sessions.pop(session_key, None)
        if conn_tuple is not None:
            conn, proto = conn_tuple
            self._logger.info(
                "%s: Closing connection for session %s (gone)",
                self.name,
                conn.session,
            )
            await proto.close()
            self.connections.pop(conn, None)
        else:
            self._logger.debug(
                "%s: No active connection found to close for session %s",
                self.name,
                session_id,
            )

    def _create_session(self, ip_address: str, player_id: int, session_id: int, publish_welcome_messages: bool):
        peername = Address(ip_address, 0)

        connection = self._connection_factory()
        if session_id is not None:
            try:
                connection.session = int(session_id)
            except (TypeError, ValueError):
                pass

        queue: asyncio.Queue = asyncio.Queue()
        protocol = RabbitMQProtocol(
            queue=queue,
            server_context=self,
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
            self.handle_client_connected(connection, protocol, peername, player_id, publish_welcome_messages)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _cleanup_sessions(self):
        now = datetime_now()
        for session_id, expiration in self.sessions_expiration.items():
            if expiration < now:
                self._logger.info("Dropping expired session %s", session_id)
                await self._remove_session(session_id)

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

        if self._channel is not None:
            await self._channel.close()
            self._channel = None

        if self._connection is not None:
            await self._connection.close()
            self._connection = None

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
        publish_welcome_messages: bool,
    ):
        try:
            await connection.on_connection_made(protocol, peername)
            await connection.on_external_auth(player_id, "broker", publish_welcome_messages)
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
