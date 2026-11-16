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
        return (
            f"You are banned from FAF {self._ban_duration_text()}. <br>"
            f"Reason: <br>{self.ban_reason}<br><br>"
            "<i>If you would like to appeal this ban, please send an email to: "
            "moderation@faforever.com</i>"
        )

    def notice(self):
        """
        Build the protocol message notifying the client about the ban.

        The human readable `text` is kept unchanged so that older clients
        render the message exactly as before. Newer clients can instead
        localize the message themselves using `i18n_key` and `i18n_args`,
        where the arguments are the ban expiry as an ISO 8601 timestamp in
        UTC and the ban reason, matching the placeholders of the
        `login.error.banned` translation. The expiry is also sent on its
        own as `expires_at` so clients can use it without having to reach
        into the translation arguments.
        """
        expires_at = self.ban_expiry.isoformat()
        return {
            "command": "notice",
            "style": "error",
            "text": self.message(),
            "i18n_key": "login.error.banned",
            "i18n_args": [expires_at, self.ban_reason],
            "expires_at": expires_at
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
