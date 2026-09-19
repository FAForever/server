"""
Common exception definitions
"""

import humanize

from server.timing import datetime_now


class ClientError(Exception):
    """
    Represents a protocol violation by the client.

    If recoverable is False, it is expected that the connection be terminated
    immediately.
    """

    def __init__(self, message, recoverable=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.recoverable = recoverable


class BanError(Exception):
    """
    Signals that an operation could not be completed because the user is banned.
    """

    def __init__(self, ban_expiry, ban_reason, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ban_expiry = ban_expiry
        self.ban_reason = ban_reason

    def message(self):
        """Return the structured localizable ban message with an ISO 8601 timestamp."""
        return {
            "key": "SERVER_ERROR_BANNED_FROM_FAF",
            "args": {
                "expires_at": self.ban_expiry.isoformat() if self.ban_expiry else "forever",
                "ban_reason": self.ban_reason
            }
        }


    def _ban_duration_text(self):
        ban_duration = self.ban_expiry - datetime_now()
        if ban_duration.days > 365 * 100:
            return "forever"
        humanized_ban_duration = humanize.precisedelta(
            ban_duration,
            minimum_unit="hours"
        )
        return f"for {humanized_ban_duration}"


class AuthenticationError(Exception):
    """
    The operation failed to authenticate.
    """

    def __init__(self, message, method, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.method = method


class DisabledError(Exception):
    """
    The operation is disabled due to an impending server shutdown.
    """
