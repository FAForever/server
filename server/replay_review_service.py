"""
Accept replay review requests from clients and publish them to the broker.

# Wire contract
The service publishes to the `MQ_EXCHANGE_NAME` topic exchange with routing
key `request.replay_review.create`. The body is a UTF-8 JSON object:

- `player_id` (int): the requesting player. **Stamped from the authenticated
  connection**, never taken from the client message.
- `login` (str): that player's name, stamped from the same place.
- `replay_id` (int): the replay to review.
- `map`, `game_mode`, `faction`, `rating`, `played_at` (str, may be empty):
  context the reviewer sees before opening the replay.
- `goal` (str, non-empty): what the player wants out of the review.
- `struggle` (str, may be empty): what went wrong from the player's view.
- `requested_at` (str): ISO 8601 UTC timestamp of when the lobby accepted it.

Consumers render this into whatever their destination wants. The lobby does
not compose prose, so the shape of a review post can change without a client
release, and a second consumer can use the same request differently.

# Why the lobby is involved at all
The point of the detour is identity. A client posting straight to a chat
service can claim to be anyone; a client sending this command is already
authenticated on the lobby socket, so the player id on the request is one the
server vouches for. Nothing else here needs the lobby.
"""

import logging
import time
from typing import Any, ClassVar, Optional

from .config import config
from .core import Service
from .decorators import with_logger
from .exceptions import ClientError
from .message_queue_service import MessageQueueService
from .players import Player
from .timing import datetime_now

REPLAY_REVIEW_ROUTING_KEY = "request.replay_review.create"

# Free text the reviewer reads. Long enough for someone to explain a game,
# short enough that a single request cannot fill a channel.
MAX_GOAL_LENGTH = 1000
MAX_STRUGGLE_LENGTH = 1000
# Everything else is a label, not prose.
MAX_LABEL_LENGTH = 100

_LABEL_FIELDS = ("map", "game_mode", "faction", "rating", "played_at")


def _clean_text(value: Any, field: str, max_length: int) -> str:
    """
    A trimmed string, or a `ClientError` naming the field that was wrong.

    Rejects non-strings rather than coercing them: a client sending a number
    where prose belongs has a bug, and silently stringifying it would put that
    bug in front of a reviewer instead of in front of its author.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ClientError(f"Invalid replay review request: {field} must be text")

    # Newlines and tabs are kept - an explanation is allowed to have
    # paragraphs - but the rest of the control range is stripped. None of it
    # can be typed deliberately, and some of it can make a rendered post look
    # like something the player did not write.
    value = "".join(
        char for char in value
        if char in ("\n", "\t") or ord(char) >= 0x20
    ).strip()

    if len(value) > max_length:
        raise ClientError(
            f"Invalid replay review request: {field} is longer than "
            f"{max_length} characters"
        )
    return value


def parse_review_request(message: dict) -> dict:
    """
    The content fields of a review request, validated.

    Deliberately excludes identity: the caller stamps `player_id` and `login`
    from the connection. Whatever the client says about who it is is dropped
    here rather than overwritten afterwards, so there is no ordering in which
    the client's version survives.

    A replay is named by id only. The client also knows how to name one by
    link or by a local file, but neither belongs on the bus: a link would let
    the client choose what a review post points at, and a file nobody else can
    fetch is not a review request. Those two cases keep using the client's own
    copy-and-paste path.
    """
    replay_id = message.get("replay_id")
    # bool is an int in Python, and `True` would otherwise sail through as
    # replay 1.
    if isinstance(replay_id, bool) or not isinstance(replay_id, int):
        raise ClientError(
            "Invalid replay review request: replay_id must be a replay number"
        )
    if replay_id <= 0:
        raise ClientError(
            "Invalid replay review request: replay_id must be positive"
        )

    goal = _clean_text(message.get("goal"), "goal", MAX_GOAL_LENGTH)
    if not goal:
        raise ClientError(
            "Invalid replay review request: say what you would like help with"
        )

    request = {
        "replay_id": replay_id,
        "goal": goal,
        "struggle": _clean_text(
            message.get("struggle"), "struggle", MAX_STRUGGLE_LENGTH
        ),
    }
    for field in _LABEL_FIELDS:
        request[field] = _clean_text(message.get(field), field, MAX_LABEL_LENGTH)

    return request


@with_logger
class ReplayReviewService(Service):
    """
    Rate limit replay review requests and publish the ones that get through.

    The limit is per player and held in memory, which makes it a spam guard
    rather than a quota: it does not survive a restart and each lobby instance
    counts on its own. That is deliberate. The cost of a duplicate request is a
    duplicate post, and the alternative is a schema migration plus a database
    write on a path that has no other reason to touch the database. A consumer
    that needs a hard guarantee can deduplicate on `player_id` itself.
    """

    _logger: ClassVar[logging.Logger]

    def __init__(self, message_queue_service: MessageQueueService):
        """Wire the broker; the cooldown table starts empty."""
        self.message_queue_service = message_queue_service
        # player id -> monotonic timestamp of their last accepted request
        self._last_accepted: dict[int, float] = {}

    def _prune(self, now: float) -> None:
        cooldown = config.REPLAY_REVIEW_COOLDOWN_SECONDS
        self._last_accepted = {
            player_id: at
            for player_id, at in self._last_accepted.items()
            if now - at < cooldown
        }

    def seconds_until_allowed(self, player_id: int, now: float) -> float:
        """How long this player still has to wait; `0` if they may request."""
        last = self._last_accepted.get(player_id)
        if last is None:
            return 0.0
        remaining = config.REPLAY_REVIEW_COOLDOWN_SECONDS - (now - last)
        return max(0.0, remaining)

    async def submit(
        self,
        player: Player,
        request: dict,
        now: Optional[float] = None,
    ) -> None:
        """
        Publish one validated request on behalf of an authenticated player.

        Raises `ClientError` if the player is still inside their cooldown, and
        does so before anything is published: a rejected request never reaches
        the bus, so abuse costs a consumer nothing.
        """
        if now is None:
            now = time.monotonic()
        self._prune(now)

        remaining = self.seconds_until_allowed(player.id, now)
        if remaining > 0:
            hours = int(remaining // 3600) + 1
            raise ClientError(
                "You have already requested a replay review recently. You can "
                f"request another one in about {hours} hour(s).",
                recoverable=True,
            )

        payload = {
            "player_id": player.id,
            "login": player.login,
            "requested_at": datetime_now().isoformat(),
            **request,
        }

        # Claimed before the publish rather than after it. A connection's
        # messages are dispatched one at a time, so the window only exists
        # while one player has two connections, but ordering it this way costs
        # nothing and the rollback is worth having on its own: a request that
        # never reached the broker should not cost the player their turn.
        self._last_accepted[player.id] = now
        try:
            await self.message_queue_service.publish(
                config.MQ_EXCHANGE_NAME,
                REPLAY_REVIEW_ROUTING_KEY,
                payload,
            )
        except BaseException:
            self._last_accepted.pop(player.id, None)
            raise

        self._logger.info(
            "Published replay review request for player %s, replay %s",
            player.id,
            request["replay_id"],
        )
