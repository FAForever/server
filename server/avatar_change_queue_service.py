"""RabbitMQ consumer that refreshes player avatars from DB on update events."""

import json
import logging
import socket
from typing import Any, ClassVar, Optional

from aio_pika.abc import AbstractIncomingMessage, AbstractQueue

from .config import config
from .core import Service
from .decorators import with_logger
from .message_queue_service import MessageQueueService
from .player_service import PlayerService

PLAYER_AVATAR_UPDATE_ROUTING_KEY = "success.player_avatar.update"


@with_logger
class AvatarChangeQueueService(Service):

    """
    Consume `success.player_avatar.update` messages and refresh players.

    Wire contract
    -------------
    Publishers post to the `MQ_EXCHANGE_NAME` topic exchange with routing
    key `success.player_avatar.update`. The body is a UTF-8 JSON object:

    - `player_id` (int, required): the player whose selected avatar changed.
    - `avatar_id` (int or null, optional): the newly selected avatar id, or
      null if the player cleared their avatar. The lobby itself ignores this
      field — it always re-reads the DB so it gets the matching url/tooltip
      and applies the ownership check. The field is shipped for the benefit
      of other subscribers that may want to act on the change without an
      extra DB roundtrip.

    On receipt the lobby re-reads the affected player's avatar from the DB
    and marks them dirty so the existing `BroadcastService` emits a
    `player_info` to every connected client on its next tick.
    """

    _logger: ClassVar[logging.Logger]

    def __init__(
        self,
        message_queue_service: MessageQueueService,
        player_service: PlayerService,
    ):
        """Wire dependencies; consumer is started in `initialize`."""
        self.message_queue_service = message_queue_service
        self.player_service = player_service
        self._queue: Optional[AbstractQueue] = None
        self._consumer_tag: Optional[str] = None

    async def initialize(self) -> None:
        # Per-instance queue: every lobby pod must process every event so
        # whichever pod is hosting the player can refresh its in-memory
        # state. Naming follows `<exchange>.<service>.<routing-key>.<host>`,
        # matching `ClientMessageQueueService`.
        queue_name = (
            f"{config.MQ_EXCHANGE_NAME}.lobby.player_avatar.update"
            f".{socket.gethostname()}"
        )
        result = await self.message_queue_service.declare_queue_and_consume(
            exchange_name=config.MQ_EXCHANGE_NAME,
            routing_key=PLAYER_AVATAR_UPDATE_ROUTING_KEY,
            callback=self._on_message,
            queue_name=queue_name,
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
                    "Dropping avatar-update message with non-JSON body"
                )
                return

            if not isinstance(payload, dict):
                self._logger.warning(
                    "Dropping avatar-update message: payload is not a JSON object"
                )
                return

            raw_player_id: Any = payload.get("player_id")
            # Reject bool explicitly: int(True) == 1 would otherwise sneak
            # through and refresh player 1 on every truthy payload.
            if isinstance(raw_player_id, bool):
                self._logger.warning(
                    "Dropping avatar-update message: invalid player_id %r",
                    raw_player_id,
                )
                return
            try:
                player_id = int(raw_player_id)
            except (TypeError, ValueError):
                self._logger.warning(
                    "Dropping avatar-update message: invalid player_id %r",
                    raw_player_id,
                )
                return

            refreshed = await self.player_service.refresh_player_avatar(player_id)
            if not refreshed:
                self._logger.debug(
                    "avatar-update for player %s ignored: not connected here",
                    player_id,
                )
