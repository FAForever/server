from datetime import datetime

import humanize


class ClientError(Exception):
    """
    Represents a ClientError

    If recoverable is False, it is expected that the
    connection be terminated immediately.
    """
    def __init__(self, message, recoverable=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.recoverable = recoverable


class BanError(Exception):
    def __init__(self, ban_expiry, ban_reason, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ban_expiry = ban_expiry
        self.ban_reason = ban_reason

    def message(self):
        return (f"You are banned from FAF {self._ban_duration_text()}. <br>"
                f"Reason : <br>"
                f"{self.ban_reason}")

    def _ban_duration_text(self):
        ban_duration = self.ban_expiry - datetime.utcnow()
        if ban_duration.days > 365 * 100:
            return "forever"
        humanized_ban_duration = humanize.precisedelta(
            ban_duration,
            minimum_unit="hours"
        )
        return f"for {humanized_ban_duration}"


class AuthenticationError(Exception):
    def __init__(self, message, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
