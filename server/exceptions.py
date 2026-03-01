"""
Common exception definitions
"""



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

    def as_payload(self):
        expires_at = None
        if self.ban_expiry is not None:
            expires_at = self.ban_expiry.isoformat()

        return {
            "command": "banned",
            "expires_at": expires_at,
            "reason": self.ban_reason,
        }

    def message(self):
        # Keep a non-localized internal abort message for connection logs.
        if self.ban_expiry is None:
            return "banned (expires: never)"
        return f"banned (expires: {self.ban_expiry.isoformat()})"


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
