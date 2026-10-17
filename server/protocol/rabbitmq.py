"""RabbitMQ wire protocol: consumes from a queue and publishes via MessageQueueService."""

import asyncio
import json
from typing import Optional

from aio_pika import DeliveryMode

import server.metrics as metrics
from .protocol import DisconnectedError, Protocol, json_encoder
from ..config import config
from ..message_queue_service import MessageQueueService

_SENTINEL = object()


class RabbitMQProtocol(Protocol):
    """
    Protocol implementation that receives messages from a RabbitMQ queue
    and sends messages by publishing via MessageQueueService.
    All messages are assumed to be dictionary objects.
    """

    def __init__(
            self,
            queue: asyncio.Queue,
            message_queue_service: MessageQueueService,
            session: int,
    ):
        """
        Wrap a queue providing messages and message queue service.

        # Parameters
        - queue: queue providing incoming messages
        - message_queue_service: MessageQueueService instance used for publishing messages
        - session: session id for the protocol
        """
        self.queue = queue
        self.message_queue_service = message_queue_service
        self.exchange_name = config.OUTBOUND_EXCHANGE_NAME
        self.session = session

        self._pending: set[asyncio.Task] = set()
        self._closed = False

    @staticmethod
    def encode_message(message: dict) -> bytes:
        return json_encoder.encode(message).encode()

    @staticmethod
    def decode_message(data: bytes) -> dict:
        return json.loads(data)

    def is_connected(self) -> bool:
        if self._closed:
            return False
        return True

    async def read_message(self) -> dict:
        if not self.is_connected():
            raise DisconnectedError("RabbitMQ protocol is not connected!")

        item = await self.queue.get()
        if item is _SENTINEL or not self.is_connected():
            raise DisconnectedError("RabbitMQ connection closed")

        return item

    def write_message(
            self,
            message: dict,
            routing_key: Optional[str] = None,
            exchange_name: Optional[str] = None,
            mandatory: Optional[bool] = None,
            delivery_mode: Optional[DeliveryMode] = None,
            **kwargs,
    ) -> None:
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")
        if self.message_queue_service is None:
            raise DisconnectedError("No message queue service configured for publishing!")

        task = asyncio.create_task(
            self.message_queue_service.publish(
                exchange_name=config.OUTBOUND_EXCHANGE_NAME,
                routing="",
                payload=self._wrap_message_with_session(message),
            )
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def write_messages(
            self,
            messages: list[dict],
    ) -> None:
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        if not self.is_connected():
            raise DisconnectedError("Protocol is not connected!")
        if self.message_queue_service is None:
            raise DisconnectedError("No message queue service configured for publishing!")

        task = asyncio.create_task(
            self.message_queue_service.publish_many(
                exchange_name=config.OUTBOUND_EXCHANGE_NAME,
                routing="",
                payloads=[self._wrap_message_with_session(message) for message in messages],
            )
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def write_raw(self, data: bytes) -> None:
        payload = self.decode_message(data)
        self.write_message(payload)

    def _wrap_message_with_session(self, payload: dict) -> dict:
        return {"target": {"@type": "session", "session_id": self.session}, "message": payload}


    async def drain(self) -> None:
        if not self._pending:
            return
        try:
            await asyncio.gather(*self._pending)
        except Exception as e:
            await self.close()
            raise DisconnectedError("Protocol connection lost!") from e

    def abort(self) -> None:
        self._closed = True
        for task in self._pending:
            task.cancel()
        self.queue.put_nowait(_SENTINEL)

    async def close(self) -> None:
        self._closed = True
        if (
                self.queue is not None
        ):
            self.queue.put_nowait(_SENTINEL)
