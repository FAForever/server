"""
Interfaces with RabbitMQ
"""

import asyncio
import json

import aio_pika
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.exceptions import ProbableAuthenticationError

from .asyncio_extensions import synchronizedmethod
from .config import TRACE, config
from .core import Service
from .decorators import with_logger


class ConnectionAttemptFailed(ConnectionError):
    pass


@with_logger
class MessageQueueService(Service):
    """
    Service handling connection to the message queue
    and providing an interface to publish messages.
    """

    def __init__(self) -> None:
        self._connection = None
        self._channel = None
        self._exchanges = {}
        self._exchange_types = {}
        self._is_ready = False

        config.register_callback("MQ_USER", self.reconnect)
        config.register_callback("MQ_PASSWORD", self.reconnect)
        config.register_callback("MQ_VHOST", self.reconnect)
        config.register_callback("MQ_SERVER", self.reconnect)
        config.register_callback("MQ_PORT", self.reconnect)

    @synchronizedmethod("initialization_lock")
    async def initialize(self) -> None:
        if self._is_ready:
            return

        try:
            await self._connect()
        except ConnectionAttemptFailed:
            return
        self._is_ready = True

        await self._declare_exchange(config.MQ_EXCHANGE_NAME, ExchangeType.TOPIC)

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
        except ConnectionError as e:
            self._logger.warning(
                "Unable to connect to RabbitMQ. Is it running?", exc_info=True
            )
            raise ConnectionAttemptFailed from e
        except ProbableAuthenticationError as e:
            self._logger.warning(
                "Unable to connect to RabbitMQ. Incorrect credentials?", exc_info=True
            )
            raise ConnectionAttemptFailed from e
        except Exception as e:
            self._logger.warning(
                "Unable to connect to RabbitMQ due to unhandled excpetion %s. Incorrect vhost?",
                e,
                exc_info=True,
            )
            raise ConnectionAttemptFailed from e

        self._channel = await self._connection.channel(publisher_confirms=False)
        self._logger.debug("Connected to RabbitMQ %r", self._connection)

    async def declare_exchange(
        self, exchange_name: str, exchange_type: ExchangeType = ExchangeType.TOPIC, durable: bool = True
    ) -> None:
        await self.initialize()
        if not self._is_ready:
            self._logger.warning(
                "Not connected to RabbitMQ, unable to declare exchange."
            )
            return

        await self._declare_exchange(exchange_name, exchange_type, durable)

    async def _declare_exchange(
        self, exchange_name: str, exchange_type: ExchangeType, durable: bool = True
    ) -> None:
        new_exchange = await self._channel.declare_exchange(
            exchange_name, exchange_type, durable
        )

        self._exchanges[exchange_name] = new_exchange
        self._exchange_types[exchange_name] = exchange_type

    @synchronizedmethod("initialization_lock")
    async def shutdown(self) -> None:
        self._is_ready = False
        await self._shutdown()

    async def _shutdown(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None

        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def publish(
        self,
        exchange_name: str,
        routing: str,
        payload: dict,
        mandatory: bool = False,
        delivery_mode: DeliveryMode = DeliveryMode.PERSISTENT,
    ) -> None:
        if not self._is_ready:
            self._logger.warning(
                "Not connected to RabbitMQ, unable to publish message."
            )
            return

        exchange = self._exchanges.get(exchange_name)
        if exchange is None:
            raise KeyError(f"Unknown exchange {exchange_name}.")

        message = aio_pika.Message(
            json.dumps(payload).encode(), delivery_mode=delivery_mode
        )

        async with self._channel.transaction():
            await exchange.publish(
                message,
                routing_key=routing,
                mandatory=mandatory
            )
            self._logger.log(
                TRACE, "Published message %s to %s/%s", payload, exchange_name, routing
            )

    @synchronizedmethod("initialization_lock")
    async def reconnect(self) -> None:
        self._is_ready = False
        await self._shutdown()

        try:
            await self._connect()
        except ConnectionAttemptFailed:
            return

        for exchange_name in list(self._exchanges.keys()):
            await self._declare_exchange(
                exchange_name, self._exchange_types[exchange_name]
            )
        self._is_ready = True
