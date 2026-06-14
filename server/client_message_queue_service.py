"""Forward RabbitMQ messages from trusted microservices to connected clients.

# Wire contract
Publishers post to the `MQ_EXCHANGE_NAME` topic exchange with routing key
`client.push`. Addressing lives in AMQP message headers:

- `user-id` (int, optional): forward the body to the player with this id, if
  connected to this lobby instance. If not connected, the message is logged
  and acked.
- `channel` (str, optional, reserved): future per-channel pub/sub. Currently
  recognised but not yet implemented.
- If neither header is set, the message is broadcast to every authenticated
  client connected to this instance.

The message body is a UTF-8 JSON object and is forwarded to the client
verbatim. The lobby server does not validate or rewrap it; producers are
trusted because the broker is reachable only from internal services.
"""

import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from aio_pika.abc import AbstractIncomingMessage, AbstractQueue

from .config import config
from .core import Service
from .decorators import with_logger
from .message_queue_service import MessageQueueService
from .player_service import PlayerService

if TYPE_CHECKING:
    from server import ServerInstance


CLIENT_PUSH_ROUTING_KEY = "client.push"


@with_logger
class ClientMessageQueueService(Service):

    """Consume `client.push` messages and forward them to local clients."""

    _logger: ClassVar[logging.Logger]

    def __init__(
        self,
        server: "ServerInstance",
        message_queue_service: MessageQueueService,
        player_service: PlayerService,
    ):
        """Wire dependencies; consumer is started in `initialize`."""
        self.server = server
        self.message_queue_service = message_queue_service
        self.player_service = player_service
        self._queue: Optional[AbstractQueue] = None
        self._consumer_tag: Optional[str] = None

    async def initialize(self) -> None:
        result = await self.message_queue_service.declare_queue_and_consume(
            exchange_name=config.MQ_EXCHANGE_NAME,
            routing_key=CLIENT_PUSH_ROUTING_KEY,
            callback=self._on_message,
        )
        if result is not None:
            self._queue, self._consumer_tag = result

    async def shutdown(self) -> None:
        if self._queue is not None and self._consumer_tag is not None:
            await self._queue.cancel(self._consumer_tag)
        self._queue = None
        self._consumer_tag = None

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                payload = json.loads(message.body)
            except (ValueError, UnicodeDecodeError):
                self._logger.warning(
                    "Dropping client-push message with non-JSON body"
                )
                return

            if not isinstance(payload, dict):
                self._logger.warning(
                    "Dropping client-push message: payload is not a JSON object"
                )
                return

            headers = message.headers or {}
            user_id = headers.get("user-id")
            channel = headers.get("channel")

            if user_id is not None:
                self._dispatch_to_user(user_id, payload)
            elif channel is not None:
                self._logger.info(
                    "client-push channel %r received but channel routing is "
                    "not yet implemented; dropping",
                    channel,
                )
            else:
                self.server.write_broadcast(payload)

    def _dispatch_to_user(self, user_id: Any, payload: dict) -> None:
        try:
            player_id = int(user_id)
        except (TypeError, ValueError):
            self._logger.warning(
                "Dropping client-push message: invalid user-id %r", user_id
            )
            return

        player = self.player_service[player_id]
        if player is None:
            self._logger.info(
                "client-push for user %s ignored: not connected here",
                player_id,
            )
            return

        player.write_message(payload)
