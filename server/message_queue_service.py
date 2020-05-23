import asyncio
import json
from typing import Dict

import aio_pika
from aio_pika import DeliveryMode, ExchangeType

from .config import config
from .core import Service
from .decorators import with_logger


@with_logger
class MessageQueueService(Service):
    def __init__(self) -> None:
        self._logger.info("Message queue service created.")
        self._connection = None
        self._channel = None
        self._exchanges = {}

    async def initialize(self) -> None:
        if self._connection is not None:
            return

        await self._connect()

    async def _connect(self) -> None:
        self._connection = await aio_pika.connect_robust(
            "amqp://{user}:{password}@localhost:{port}/{vhost}".format(
                user=config.MQ_USER,
                password=config.MQ_PASSWORD,
                vhost=config.MQ_VHOST,
                port=config.MQ_PORT,
            ),
            loop=asyncio.get_running_loop(),
        )
        self._channel = await self._connection.channel(publisher_confirms=False)
        self._logger.debug("Connected to RabbitMQ %r", self._connection)

    async def declare_exchange(
        self, exchange_name: str, exchange_type: ExchangeType = ExchangeType.TOPIC
    ) -> None:
        new_exchange = await self._channel.declare_exchange(
            exchange_name, exchange_type
        )

        self._exchanges[exchange_name] = new_exchange

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
