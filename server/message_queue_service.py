import asyncio
import json
from typing import Dict

import aio_pika
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.exceptions import ProbableAuthenticationError

from .config import config
from .core import Service
from .decorators import with_logger


@with_logger
class MessageQueueService(Service):
    def __init__(self) -> None:
        """
        Service handling connection to the message queue
        and providing an interface to publish messages.
        """
        self._logger.info("Message queue service created.")
        self._connection = None
        self._channel = None
        self._exchanges = {}
        self._exchange_types = {}

        config.register_callback("MQ_USER", self.reconnect)
        config.register_callback("MQ_PASSWORD", self.reconnect)
        config.register_callback("MQ_VHOST", self.reconnect)
        config.register_callback("MQ_PORT", self.reconnect)

    async def initialize(self) -> None:
        if self._connection is not None:
            return

        await self._connect()

    async def _connect(self) -> None:
        try:
            self._connection = await aio_pika.connect_robust(
                "amqp://{user}:{password}@localhost:{port}/{vhost}".format(
                    user=config.MQ_USER,
                    password=config.MQ_PASSWORD,
                    vhost=config.MQ_VHOST,
                    port=config.MQ_PORT,
                ),
                loop=asyncio.get_running_loop(),
            )
        except ConnectionError:
            self._logger.warning("Unable to connect to RabbitMQ. Is it running?")
            return
        except ProbableAuthenticationError:
            self._logger.warning(
                "Unable to connect to RabbitMQ. Incorrect credentials?"
            )
            return
        except Exception as e:
            self._logger.warning(
                "Unable to connect to RabbitMQ due to unhandled excpetion %s. Incorrect vhost?",
                e,
            )
            return

        self._channel = await self._connection.channel(publisher_confirms=False)
        self._logger.debug("Connected to RabbitMQ %r", self._connection)

    async def declare_exchange(
        self, exchange_name: str, exchange_type: ExchangeType = ExchangeType.TOPIC
    ) -> None:
        if self._connection is None:
            self._logger.warning(
                "Not connected to RabbitMQ, unable to declare exchange."
            )
            return

        new_exchange = await self._channel.declare_exchange(
            exchange_name, exchange_type
        )

        self._exchanges[exchange_name] = new_exchange
        self._exchange_types[exchange_name] = exchange_type

    async def shutdown(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def publish(
        self,
        exchange_name: str,
        routing: str,
        payload: Dict,
        delivery_mode: DeliveryMode = DeliveryMode.PERSISTENT,
    ) -> None:
        if self._connection is None:
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
            await exchange.publish(message, routing_key=routing)
            self._logger.debug(
                "Published message %s to %s/%s", payload, exchange_name, routing
            )

    async def reconnect(self) -> None:
        await self.shutdown()
        await self.initialize()

        for exchange_name in list(self._exchanges.keys()):
            self.declare_exchange(exchange_name, self._exchange_types[exchange_name])
