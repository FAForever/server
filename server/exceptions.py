"""
Common exception definitions
"""

from datetime import timezone

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

    def to_payload(self):
        expiry_utc = self.ban_expiry.astimezone(timezone.utc)
        return {
            "command": "banned",
            "expires_at": expiry_utc.isoformat(),
            "reason": self.ban_reason,
        }


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
