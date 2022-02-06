from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import humanize

from server.core import Service
from server.decorators import with_logger
from server.players import Player
from server.timing import at_interval, datetime_now


@dataclass
class Violation():
    count: int
    time: datetime

    def __init__(self, count: int = 1, time: Optional[datetime] = None):
        self.count = count
        self.time = time or datetime_now()

    def register(self):
        self.count += 1
        self.time = datetime_now()

    def get_ban_expiration(self) -> datetime:
        if self.count < 2:
            # No ban, expires as soon as it's registered
            return self.time
        elif self.count == 2:
            return self.time + timedelta(minutes=10)
        else:
            return self.time + timedelta(minutes=30)

    def get_remaining(self, now: Optional[datetime] = None) -> timedelta:
        return self.get_ban_expiration() - (now or datetime_now())

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """
        Whether the violation history should be reset. This is different from
        the ban expiration time which should be checked by calling
        `get_ban_expiration`.
        """
        now = now or datetime_now()
        # TODO: Config?
        return self.time + timedelta(hours=1) <= now

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "time": self.time.isoformat()
        }


@with_logger
class ViolationService(Service):
    """
    Track who is banned from searching and for how long. Apply progressive
    discipline for repeated violations.

    A violation could be anything, but it is usually any time a player fails
    to connect to a game.
    """

    def __init__(self):
        self.violations: dict[Player, Violation] = {}

    async def initialize(self):
        self._cleanup_task = at_interval(5, func=self.clear_expired)

    def clear_expired(self):
        now = datetime_now()
        for player, violation in list(self.violations.items()):
            if violation.is_expired(now):
                self._clear_violation(player)

    def register_violations(self, players: list[Player]):
        now = datetime_now()
        for player in players:
            violation = self.violations.get(player)
            if violation is None or violation.is_expired(now):
                violation = Violation(time=now)
                self.violations[player] = violation
            else:
                violation.register()

            player.write_message({
                "command": "search_violation",
                **violation.to_dict()
            })
            extra_text = ""
            if violation.count > 1:
                delta_text = humanize.naturaldelta(
                    violation.get_ban_expiration() - now
                )
                extra_text = f" You can queue again in {delta_text}"
            player.write_message({
                "command": "notice",
                "style": "info",
                "text": (
                    f"You have received {violation.count} violations." +
                    extra_text
                )
            })

    def get_violations(self, players: list[Player]) -> dict[Player, Violation]:
        now = datetime_now()
        result = {}
        for player in players:
            violation = self.violations.get(player)
            if not violation:
                continue
            elif violation.get_ban_expiration() > now:
                result[player] = violation
            elif violation.is_expired(now):
                self._clear_violation(player)

        return result

    def _clear_violation(self, player: Player):
        violation = self.violations.get(player)
        self._logger.debug(
            "Cleared violation for player %s: %s",
            player.login,
            violation
        )
        del self.violations[player]
